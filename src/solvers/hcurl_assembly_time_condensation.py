"""Assembly-time cell-interior condensation for affine H(curl) hexahedra.

The established Task035b condensation path starts from a fully assembled
operator.  This module instead calls the compiled FFCx cell kernel directly,
applies the DOLFINx H(curl) orientation transforms, forms the local Schur
complement, and inserts only trace rows into PETSc.

The first implementation is deliberately narrow and fail-closed:

* complex128, scalar-blocked H(curl);
* first-order, axis-aligned affine hexahedral geometry;
* cell integrals with embedded constants and no runtime coefficients;
* every locally owned cell must have an explicit integral subdomain tag.

Identical ``(material tag, cell widths, orientation)`` classes reuse the
condensed tensor and the interior-recovery operator.  Ordinary assembly remains
the default elsewhere.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from time import perf_counter
from types import MappingProxyType
from typing import Any, Callable
import warnings

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy import sparse
from scipy.linalg import LinAlgWarning, lu_factor, lu_solve


def assembly_time_condensation_capacity_facts(
    *,
    dimension: int,
    interior_dimension: int,
    trace_dimension: int,
    raw_class_count: int,
    oriented_class_count: int,
    identity_class_count: int,
    retain_local_schur: bool,
    scalar_bytes: int,
    index_bytes: int,
    real_bytes: int,
) -> dict[str, int | bool | str]:
    """Return the existing class-shape allocation formulas.

    The assembly builder uses these same formulas for its preallocation gate.
    V22 may bind the formula to the already-qualified B class dimensions
    before the p6 action is constructed; it must not grow a second metadata
    collector or substitute global vector lengths for local class shapes.
    """

    dimensions = {
        "dimension": dimension,
        "interior_dimension": interior_dimension,
        "trace_dimension": trace_dimension,
        "raw_class_count": raw_class_count,
        "oriented_class_count": oriented_class_count,
        "identity_class_count": identity_class_count,
        "scalar_bytes": scalar_bytes,
        "index_bytes": index_bytes,
        "real_bytes": real_bytes,
    }
    if any(type(value) is not int or value < 0 for value in dimensions.values()):
        raise ValueError("condensation capacity dimensions must be non-negative integers")
    if dimension <= 0 or interior_dimension <= 0 or trace_dimension <= 0:
        raise ValueError("condensation class dimensions must be positive")
    if oriented_class_count == 0:
        raise ValueError("condensation capacity requires an oriented class")
    full_tensor_bytes = dimension * dimension * scalar_bytes
    schur_bytes = trace_dimension * trace_dimension * scalar_bytes
    retained_per_oriented_class = (
        interior_dimension * interior_dimension * scalar_bytes
        + interior_dimension * index_bytes
        + 2 * interior_dimension * trace_dimension * scalar_bytes
        + (schur_bytes if retain_local_schur else 0)
    )
    identity_cache_bytes_upper = (
        identity_class_count
        * interior_dimension
        * interior_dimension
        * real_bytes
    )
    raw_cache_bytes_upper = raw_class_count * full_tensor_bytes
    oriented_tensor_bytes_upper = oriented_class_count * full_tensor_bytes
    schur_cache_bytes_upper = oriented_class_count * schur_bytes
    local_working_bytes_upper = (
        3 * full_tensor_bytes
        + interior_dimension * interior_dimension * scalar_bytes
        + interior_dimension * index_bytes
        + 2 * interior_dimension * trace_dimension * scalar_bytes
        + 2 * schur_bytes
    )
    retained_schur_term = "t*t*s" if retain_local_schur else "0"
    return {
        "full_tensor_bytes": full_tensor_bytes,
        "schur_bytes": schur_bytes,
        "retained_per_oriented_class_bytes": retained_per_oriented_class,
        "identity_cache_bytes_upper": identity_cache_bytes_upper,
        "retained_numeric_bytes_upper": (
            oriented_class_count * retained_per_oriented_class
            + identity_cache_bytes_upper
        ),
        "raw_cache_bytes_upper": raw_cache_bytes_upper,
        "oriented_tensor_bytes_upper": oriented_tensor_bytes_upper,
        "schur_cache_bytes_upper": schur_cache_bytes_upper,
        "local_working_bytes_upper": local_working_bytes_upper,
        "workspace_bytes_upper": (
            raw_cache_bytes_upper
            + oriented_tensor_bytes_upper
            + schur_cache_bytes_upper
            + local_working_bytes_upper
        ),
        "retain_local_schur": bool(retain_local_schur),
        "formula": (
            "retained=o*(i*i*s+i*index+2*i*t*s+"
            f"{retained_schur_term})+{identity_class_count}*i*i*real; "
            "workspace=r*F+o*F+o*T+(3*F+i*i*s+i*index+2*i*t*s+2*T)"
        ),
    }


def _idx(values) -> np.ndarray:
    if isinstance(values, np.ndarray):
        return np.asarray(values, dtype=PETSc.IntType)
    return np.fromiter(values, dtype=PETSc.IntType)


def _checked_petsc_index_scalar(value: int, name: str) -> int:
    """Check a wide Python count before it is used as a PETSc index."""

    wide = int(value)
    limits = np.iinfo(PETSc.IntType)
    if wide < int(limits.min) or wide > int(limits.max):
        raise OverflowError(f"{name}={wide} does not fit PETSc.IntType")
    return wide


def _checked_petsc_index_array(values: Any, name: str) -> np.ndarray:
    """Convert wide integer rows only after proving every value fits PETSc."""

    wide = np.asarray(values, dtype=np.int64)
    limits = np.iinfo(PETSc.IntType)
    if wide.size and (
        int(wide.min()) < int(limits.min) or int(wide.max()) > int(limits.max)
    ):
        raise OverflowError(f"{name} contains values outside PETSc.IntType")
    return np.asarray(wide, dtype=PETSc.IntType)


@dataclass(frozen=True)
class CellRecoveryMap:
    """Numbering and cached class identity needed for one owned cell."""

    interior_original_dofs: np.ndarray
    trace_original_dofs: np.ndarray
    class_key: tuple[Any, ...]


@dataclass(frozen=True)
class _DenseIndexMapping(Mapping[int, int]):
    """Compact global-row lookup backed by one signed integer array."""

    lookup: np.ndarray
    item_count: int

    def __getitem__(self, key: int) -> int:
        if isinstance(key, bool) or not isinstance(key, (int, np.integer)):
            raise KeyError(key)
        row = int(key)
        if row < 0 or row >= len(self.lookup):
            raise KeyError(key)
        value = int(self.lookup[row])
        if value < 0:
            raise KeyError(key)
        return value

    def __iter__(self):
        return (int(row) for row in np.flatnonzero(self.lookup >= 0))

    def __len__(self) -> int:
        return int(self.item_count)


@dataclass(frozen=True)
class _CompactTraceExpansionMapping(Mapping[int, tuple[np.ndarray, np.ndarray]]):
    """Identity-by-default trace expansion with CSR storage only for slaves."""

    trace_rows: _DenseIndexMapping
    active_rows: _DenseIndexMapping
    slave_ordinals: np.ndarray
    indptr: np.ndarray
    indices: np.ndarray
    coefficients: np.ndarray

    def __getitem__(self, key: int) -> tuple[np.ndarray, np.ndarray]:
        if isinstance(key, bool) or not isinstance(key, (int, np.integer)):
            raise KeyError(key)
        row = int(key)
        if row < 0 or row >= len(self.active_rows.lookup):
            raise KeyError(key)
        active = self.active_rows.lookup[row]
        if active >= 0:
            return (
                np.asarray([active], dtype=PETSc.IntType),
                np.ones(1, dtype=np.complex128),
            )
        ordinal = self.slave_ordinals[row]
        if ordinal < 0:
            raise KeyError(key)
        start, stop = int(self.indptr[ordinal]), int(self.indptr[ordinal + 1])
        return self.indices[start:stop], self.coefficients[start:stop]

    def __iter__(self):
        return iter(self.trace_rows)

    def __len__(self) -> int:
        return len(self.trace_rows)

    def expand_rows(
        self, trace_original: np.ndarray
    ) -> tuple[np.ndarray, sparse.csr_matrix, bool]:
        rows_wide = np.asarray(trace_original, dtype=np.int64).reshape(-1)
        rows = _checked_petsc_index_array(rows_wide, "compact trace expansion rows")
        if rows.size and (
            int(rows.min()) < 0 or int(rows.max()) >= len(self.active_rows.lookup)
        ):
            raise ValueError("compact trace expansion row lies outside the global space")
        active = self.active_rows.lookup[rows].astype(PETSc.IntType, copy=False)
        if np.all(active >= 0):
            unique = np.unique(active)
            columns = np.searchsorted(unique, active).astype(np.int32, copy=False)
            identity = len(unique) == len(rows) and np.array_equal(active, unique)
            if identity:
                return unique, sparse.eye(len(rows), dtype=np.complex128, format="csr"), True
            expansion = sparse.csr_matrix(
                (
                    np.ones(len(rows), dtype=np.complex128),
                    (np.arange(len(rows), dtype=np.int32), columns),
                ),
                shape=(len(rows), len(unique)),
            )
            return unique, expansion, False

        row_parts: list[np.ndarray] = []
        id_parts: list[np.ndarray] = []
        value_parts: list[np.ndarray] = []
        identity = len(rows) > 0
        for row_index, original in enumerate(rows):
            active_id = int(self.active_rows.lookup[int(original)])
            if active_id >= 0:
                ids = np.asarray([active_id], dtype=PETSc.IntType)
                values = np.ones(1, dtype=np.complex128)
                if active_id != row_index:
                    identity = False
            else:
                ordinal = int(self.slave_ordinals[int(original)])
                if ordinal < 0:
                    raise KeyError(int(original))
                start, stop = int(self.indptr[ordinal]), int(self.indptr[ordinal + 1])
                ids = self.indices[start:stop]
                values = self.coefficients[start:stop]
                identity = False
            row_parts.append(np.full(len(ids), row_index, dtype=np.int32))
            id_parts.append(np.asarray(ids, dtype=PETSc.IntType))
            value_parts.append(np.asarray(values, dtype=np.complex128))
        all_ids = np.concatenate(id_parts) if id_parts else np.empty(0, dtype=PETSc.IntType)
        unique = np.unique(all_ids)
        columns = np.searchsorted(unique, all_ids).astype(np.int32, copy=False)
        row_ids = np.concatenate(row_parts) if row_parts else np.empty(0, dtype=np.int32)
        values = np.concatenate(value_parts) if value_parts else np.empty(0, dtype=np.complex128)
        expansion = sparse.csr_matrix(
            (values, (row_ids, columns)), shape=(len(rows), len(unique))
        )
        expansion.sum_duplicates()
        expansion.sort_indices()
        return unique, expansion, identity and len(unique) == len(rows)


@dataclass(frozen=True)
class TraceConstraintMap:
    """Sparse full-trace to independent-trace expansion ``u_t = C_t q``."""

    owned_active_original_dofs: np.ndarray
    original_to_active: Mapping[int, int]
    expansion_by_original: Mapping[int, tuple[np.ndarray, np.ndarray]]
    full_trace_rows: int
    active_rows: int
    slave_rows: int
    owned_active_range: tuple[int, int]
    build_audit: dict[str, Any]

    def __post_init__(self) -> None:
        owned = np.asarray(self.owned_active_original_dofs)
        start, stop = (int(value) for value in self.owned_active_range)
        if (
            owned.ndim != 1
            or owned.dtype.kind not in "iu"
            or owned.dtype.kind == "b"
            or (owned.size > 1 and np.any(owned[1:] <= owned[:-1]))
            or start < 0
            or stop < start
            or stop > int(self.active_rows)
            or stop - start != len(owned)
        ):
            raise ValueError("owned active trace rows must be sorted and match their active range")

    def map_original_rows(self, original_rows: Any) -> np.ndarray:
        """Map a batch of independent original rows to active trace rows.

        The batch API keeps callers from repeating the mapping contract and
        allows specialized maps to replace the dictionary lookup without
        changing the carrier provider.  Missing rows fail closed.
        """
        rows = np.asarray(original_rows)
        if rows.ndim != 1 or rows.dtype.kind not in "iu" or rows.dtype.kind == "b":
            raise ValueError("original trace rows must be a one-dimensional integer array")
        start, stop = (int(value) for value in self.owned_active_range)
        owned = np.asarray(self.owned_active_original_dofs)
        positions = np.searchsorted(owned, rows)
        local = positions < len(owned)
        if np.any(local):
            candidate_positions = np.flatnonzero(local)
            local[candidate_positions] = (
                owned[positions[candidate_positions]] == rows[candidate_positions]
            )
        mapped = np.empty(len(rows), dtype=PETSc.IntType)
        mapped[local] = positions[local] + start
        remote = np.flatnonzero(~local)
        if remote.size:
            try:
                mapped[remote] = np.fromiter(
                    (
                        self.original_to_active[int(rows[index])]
                        for index in remote
                    ),
                    dtype=PETSc.IntType,
                    count=len(remote),
                )
            except KeyError as exc:
                raise ValueError(
                    "original trace row is not an independent active row"
                ) from exc
        if mapped.size and (np.any(mapped < 0) or np.any(mapped >= int(self.active_rows))):
            raise RuntimeError("original trace row mapped outside the active range")
        return mapped


@dataclass
class AssemblyTimeCondensedSystem:
    """Physically reduced trace system and matrix-free recovery metadata."""

    matrix: PETSc.Mat | None
    owned_trace_original_dofs: np.ndarray
    original_to_trace: Mapping[int, int]
    trace_constraints: TraceConstraintMap
    cell_recovery_maps: tuple[CellRecoveryMap, ...]
    interior_from_trace_by_class: dict[tuple[Any, ...], np.ndarray]
    interior_lu_by_class: dict[tuple[Any, ...], tuple[np.ndarray, np.ndarray]]
    interior_rhs_projection_by_class: dict[tuple[Any, ...], np.ndarray]
    interior_solution_embedding_by_class: dict[tuple[Any, ...], np.ndarray]
    trace_from_interior_rhs_by_class: dict[tuple[Any, ...], np.ndarray]
    interior_residual_projection_by_class: dict[tuple[Any, ...], np.ndarray]
    full_rows: int
    trace_rows: int
    active_rows: int
    appended_rows: int
    interior_rows: int
    active_interior_rows: int
    build_audit: dict[str, Any]
    comm: MPI.Intracomm = field(repr=False)
    owned_active_rows: int
    owned_appended_rows: int
    retained_local_schur_by_class: Mapping[tuple[Any, ...], np.ndarray] | None = None
    _destroyed: bool = field(default=False, init=False, repr=False)

    def create_active_vector(self) -> PETSc.Vec:
        return PETSc.Vec().createMPI(
            (self.owned_active_rows, self.active_rows),
            comm=self.comm,
        )

    def create_augmented_vector(self) -> PETSc.Vec:
        return PETSc.Vec().createMPI(
            (
                self.owned_active_rows + self.owned_appended_rows,
                self.active_rows + self.appended_rows,
            ),
            comm=self.comm,
        )

    def destroy(self) -> None:
        if self._destroyed:
            return
        if self.matrix is not None:
            self.matrix.destroy()
        self._destroyed = True


def _owned_trace_numbering(
    function_space,
    local_cell_interior_dofs: tuple[np.ndarray, ...],
    *,
    compact: bool = False,
) -> tuple[np.ndarray, Mapping[int, int], int, int]:
    dofmap = function_space.dofmap
    index_map = dofmap.index_map
    comm = function_space.mesh.comm
    full_start, full_end = map(int, index_map.local_range)
    local_interior = (
        np.concatenate(local_cell_interior_dofs)
        if local_cell_interior_dofs
        else np.empty(0, dtype=PETSc.IntType)
    )
    if len(np.unique(local_interior)) != len(local_interior):
        raise ValueError("cell-interior DoFs must be locally unique")
    if len(local_interior) and (
        int(local_interior.min()) < full_start or int(local_interior.max()) >= full_end
    ):
        raise ValueError("owned cell-interior DoFs must be owned by the cell rank")
    owned_full = np.arange(full_start, full_end, dtype=PETSc.IntType)
    owned_trace = owned_full[~np.isin(owned_full, local_interior, assume_unique=True)]
    counts = comm.allgather(int(len(owned_trace)))
    trace_start = int(sum(counts[: comm.rank]))
    full_rows = int(index_map.size_global * dofmap.index_map_bs)
    trace_rows = int(sum(counts))
    if compact:
        _checked_petsc_index_scalar(full_rows, "full_rows")
        _checked_petsc_index_scalar(trace_rows, "trace_rows")
        _checked_petsc_index_scalar(trace_start, "trace_start")
        if (
            comm.size != 1
            or full_start != 0
            or full_end != full_rows
            or trace_start != 0
        ):
            raise NotImplementedError("compact action-only row maps are qualified for MPI1 ownership")
        lookup = np.full(full_rows, -1, dtype=PETSc.IntType)
        lookup[owned_trace] = _checked_petsc_index_array(
            np.arange(len(owned_trace), dtype=np.int64), "owned trace ordinals"
        )
        mapping: Mapping[int, int] = _DenseIndexMapping(lookup, trace_rows)
    else:
        packets = comm.allgather(
            (
                np.asarray(owned_trace, dtype=np.int64),
                np.arange(
                    trace_start,
                    trace_start + len(owned_trace),
                    dtype=np.int64,
                ),
            )
        )
        mapping = {}
        for originals, traces in packets:
            mapping.update(
                (int(original), int(trace))
                for original, trace in zip(originals, traces, strict=True)
            )
        if len(mapping) != trace_rows:
            raise RuntimeError("trace numbering is not globally unique")
    return owned_trace, mapping, trace_rows, full_rows


def _cell_tag_array(cell_tags, owned_cells: int) -> np.ndarray:
    tags = np.full(owned_cells, -1, dtype=np.int32)
    indices = np.asarray(cell_tags.indices, dtype=np.int32)
    values = np.asarray(cell_tags.values, dtype=np.int32)
    owned = (indices >= 0) & (indices < owned_cells)
    tags[indices[owned]] = values[owned]
    if np.any(tags < 0):
        missing = np.flatnonzero(tags < 0)
        raise ValueError(
            "assembly-time condensation requires an explicit tag for every "
            f"owned cell; missing local cells {missing[:8].tolist()}"
        )
    return tags


def _cell_integral_kernels(
    compiled_form,
    *,
    sum_duplicate_cell_integrals: bool = False,
) -> dict[int, Any]:
    ufcx_form = compiled_form.ufcx_form
    start = int(ufcx_form.form_integral_offsets[0])
    stop = int(ufcx_form.form_integral_offsets[1])
    kernels: dict[int, Any] = {}
    for position in range(start, stop):
        integral_id = int(ufcx_form.form_integral_ids[position])
        integral = ufcx_form.form_integrals[position]
        kernel = integral.tabulate_tensor_complex128
        if kernel == compiled_form.module.ffi.NULL:
            raise TypeError("compiled form does not expose a complex128 cell kernel")
        if sum_duplicate_cell_integrals:
            kernels.setdefault(integral_id, []).append(kernel)
        else:
            # Preserve the historical single-kernel map unless the caller
            # explicitly opts into the correct multi-integral profile.
            kernels[integral_id] = kernel
    if not kernels:
        raise ValueError("compiled form exposes no cell integrals")
    if int(ufcx_form.num_coefficients) != 0:
        raise NotImplementedError(
            "assembly-time condensation does not yet support runtime coefficients"
        )
    if int(ufcx_form.num_constants) != 0:
        raise NotImplementedError(
            "assembly-time condensation does not yet support runtime constants"
        )
    return kernels


def _trace_constraint_map(
    function_space,
    owned_trace: np.ndarray,
    original_to_trace: dict[int, int],
    trace_rows: int,
    mpc,
    *,
    compact: bool = False,
) -> TraceConstraintMap:
    """Build an exact distributed trace-only MPC expansion.

    The finalized ``dolfinx_mpc`` object stores master links in its augmented
    local numbering.  Constraint rows are gathered once because a locally
    owned cell may touch a trace slave owned by another rank.
    """

    comm = function_space.mesh.comm
    index_map = function_space.dofmap.index_map
    if compact:
        if comm.size != 1:
            raise NotImplementedError("compact action-only MPC maps are qualified for MPI1")
        full_rows = int(index_map.size_global)
        _checked_petsc_index_scalar(full_rows, "compact full_rows")
        local_range = tuple(map(int, index_map.local_range))
        if local_range != (0, full_rows):
            raise ValueError("compact action-only maps require contiguous MPI1 global rows")
        if mpc is not None and int(index_map.size_global) != int(
            mpc.function_space.dofmap.index_map.size_global
        ):
            raise ValueError("MPC and assembly spaces have different global sizes")
        if mpc is None:
            active_lookup = np.full(full_rows, -1, dtype=PETSc.IntType)
            active_lookup[owned_trace] = _checked_petsc_index_array(
                np.arange(len(owned_trace), dtype=np.int64), "active trace ordinals"
            )
            active_map = _DenseIndexMapping(active_lookup, len(owned_trace))
            empty_slaves = np.empty(0, dtype=PETSc.IntType)
            expansions = _CompactTraceExpansionMapping(
                trace_rows=original_to_trace, active_rows=active_map,
                slave_ordinals=np.full(full_rows, -1, dtype=PETSc.IntType),
                indptr=np.zeros(1, dtype=np.int64), indices=empty_slaves,
                coefficients=np.empty(0, dtype=np.complex128),
            )
            return TraceConstraintMap(
                owned_active_original_dofs=owned_trace.copy(),
                original_to_active=active_map,
                expansion_by_original=expansions,
                full_trace_rows=trace_rows,
                active_rows=trace_rows,
                slave_rows=0,
                owned_active_range=(0, len(owned_trace)),
                build_audit={
                    "schema_version": "task035b.trace-constraint-map.v1",
                    "status": "compact_identity_no_mpc_constraints",
                    "full_trace_rows": trace_rows,
                    "active_rows": trace_rows,
                    "slave_rows": 0,
                    "compact_dense_index_bytes": int(active_lookup.nbytes),
                    "constraint_applied_before_global_matrix_insertion": False,
                },
            )
        local_slaves = np.unique(np.asarray(mpc.slaves, dtype=np.int64).reshape(-1))
        owned_local_slaves = local_slaves[
            (local_slaves >= 0) & (local_slaves < int(index_map.size_local))
        ].astype(np.int32, copy=False)
        slave_original = _checked_petsc_index_array(
            index_map.local_to_global(owned_local_slaves), "MPC slave global rows"
        ).reshape(-1)
        if len(slave_original) and any(
            int(row) not in original_to_trace for row in slave_original
        ):
            raise ValueError("assembly-time trace condensation found non-trace MPC slaves")
        order = np.argsort(slave_original, kind="stable")
        slave_original = np.ascontiguousarray(slave_original[order], dtype=PETSc.IntType)
        owned_local_slaves = np.ascontiguousarray(owned_local_slaves[order], dtype=np.int32)
        if len(slave_original) > 1 and np.any(slave_original[1:] == slave_original[:-1]):
            raise ValueError("finalized MPC contains duplicate global slave rows")
        owned_active = owned_trace[
            ~np.isin(owned_trace, slave_original, assume_unique=False)
        ]
        _checked_petsc_index_scalar(len(owned_active), "active_rows")
        _checked_petsc_index_scalar(len(slave_original), "slave_rows")
        active_lookup = np.full(full_rows, -1, dtype=PETSc.IntType)
        active_lookup[owned_active] = _checked_petsc_index_array(
            np.arange(len(owned_active), dtype=np.int64), "active trace ordinals"
        )
        active_map = _DenseIndexMapping(active_lookup, len(owned_active))
        slave_ordinals = np.full(full_rows, -1, dtype=PETSc.IntType)
        slave_ordinals[slave_original] = _checked_petsc_index_array(
            np.arange(len(slave_original), dtype=np.int64), "slave ordinals"
        )

        raw_coefficients, raw_offsets = mpc.coefficients()
        coefficients = np.asarray(raw_coefficients, dtype=np.complex128).reshape(-1)
        offsets = np.asarray(raw_offsets, dtype=np.int64).reshape(-1)
        mpc_index_map = mpc.function_space.dofmap.index_map
        indptr = np.empty(len(slave_original) + 1, dtype=np.int64)
        indptr[0] = 0
        index_parts: list[np.ndarray] = []
        coefficient_parts: list[np.ndarray] = []
        nnz = 0
        raw_master_coefficient_count = 0
        duplicate_master_terms_coalesced = 0
        maximum_masters = 0
        for ordinal, local_slave in enumerate(owned_local_slaves):
            masters_local = np.asarray(
                mpc.masters.links(int(local_slave)), dtype=np.int32
            ).reshape(-1)
            start, stop = int(offsets[int(local_slave)]), int(offsets[int(local_slave) + 1])
            row_coefficients = coefficients[start:stop]
            if len(masters_local) != len(row_coefficients) or not len(masters_local):
                raise ValueError("MPC master and coefficient counts disagree")
            masters_original = _checked_petsc_index_array(
                mpc_index_map.local_to_global(masters_local), "MPC master global rows"
            ).reshape(-1)
            if len(masters_original) and (
                int(masters_original.min()) < 0
                or int(masters_original.max()) >= full_rows
            ):
                raise ValueError("MPC master global row lies outside the space")
            if np.any(slave_ordinals[masters_original] >= 0):
                raise NotImplementedError("compact trace expansion does not accept chained MPC rows")
            active_ids = active_lookup[masters_original]
            if np.any(active_ids < 0):
                raise ValueError("MPC trace row references a non-trace or inactive master")
            if not np.isfinite(row_coefficients).all():
                raise ValueError("MPC trace coefficients must be finite")
            raw_master_coefficient_count += len(active_ids)
            merged_ids, inverse = np.unique(active_ids, return_inverse=True)
            merged_coefficients = np.zeros(len(merged_ids), dtype=np.complex128)
            np.add.at(merged_coefficients, inverse, row_coefficients)
            duplicate_master_terms_coalesced += len(active_ids) - len(merged_ids)
            nonzero = merged_coefficients != 0.0
            merged_ids = merged_ids[nonzero]
            merged_coefficients = merged_coefficients[nonzero]
            index_parts.append(np.ascontiguousarray(merged_ids, dtype=PETSc.IntType))
            coefficient_parts.append(
                np.ascontiguousarray(merged_coefficients, dtype=np.complex128)
            )
            nnz += len(merged_ids)
            if nnz > int(np.iinfo(np.int64).max):
                raise OverflowError("compact MPC expansion nnz exceeds int64 indptr capacity")
            indptr[ordinal + 1] = nnz
            maximum_masters = max(maximum_masters, len(merged_ids))
        indices = np.concatenate(index_parts) if index_parts else np.empty(0, dtype=PETSc.IntType)
        expansion_coefficients = (
            np.concatenate(coefficient_parts)
            if coefficient_parts else np.empty(0, dtype=np.complex128)
        )
        if len(owned_active) + len(slave_original) != trace_rows:
            raise ValueError("compact trace MPC rows do not close against the complete trace map")
        expansions = _CompactTraceExpansionMapping(
            trace_rows=original_to_trace,
            active_rows=active_map,
            slave_ordinals=slave_ordinals,
            indptr=indptr,
            indices=indices,
            coefficients=expansion_coefficients,
        )
        return TraceConstraintMap(
            owned_active_original_dofs=owned_active,
            original_to_active=active_map,
            expansion_by_original=expansions,
            full_trace_rows=trace_rows,
            active_rows=len(owned_active),
            slave_rows=len(slave_original),
            owned_active_range=(0, len(owned_active)),
            build_audit={
                "schema_version": "task035b.trace-constraint-map.v1",
                "status": "compact_exact_mpc_trace_expansion_built",
                "full_trace_rows": trace_rows,
                "active_rows": len(owned_active),
                "slave_rows": len(slave_original),
                "maximum_masters_per_slave": maximum_masters,
                "raw_master_coefficient_count": raw_master_coefficient_count,
                "duplicate_master_terms_coalesced": duplicate_master_terms_coalesced,
                "master_coefficients_with_exact_zero_sum_removed": (
                    raw_master_coefficient_count
                    - duplicate_master_terms_coalesced
                    - int(nnz)
                ),
                "compact_dense_index_bytes": int(
                    original_to_trace.lookup.nbytes
                    + active_lookup.nbytes
                    + slave_ordinals.nbytes
                ),
                "compact_slave_expansion_bytes": int(
                    indptr.nbytes + indices.nbytes + expansion_coefficients.nbytes
                ),
                "constraint_applied_before_global_matrix_insertion": True,
                "embedded_identity_slave_rows_allocated": False,
            },
        )
    if mpc is None:
        active_counts = comm.allgather(int(len(owned_trace)))
        active_start = int(sum(active_counts[: comm.rank]))
        packets = comm.allgather(
            (
                np.asarray(owned_trace, dtype=np.int64),
                np.arange(
                    active_start,
                    active_start + len(owned_trace),
                    dtype=np.int64,
                ),
            )
        )
        original_to_active: dict[int, int] = {}
        for originals, active in packets:
            original_to_active.update(
                (int(original), int(reduced))
                for original, reduced in zip(originals, active, strict=True)
            )
        expansion = {
            int(original): (
                _idx([original_to_active[int(original)]]),
                np.asarray([1.0], dtype=np.complex128),
            )
            for original in original_to_trace
        }
        return TraceConstraintMap(
            owned_active_original_dofs=owned_trace.copy(),
            original_to_active=original_to_active,
            expansion_by_original=expansion,
            full_trace_rows=trace_rows,
            active_rows=trace_rows,
            slave_rows=0,
            owned_active_range=(active_start, active_start + len(owned_trace)),
            build_audit={
                "schema_version": "task035b.trace-constraint-map.v1",
                "status": "identity_no_mpc_constraints",
                "full_trace_rows": trace_rows,
                "active_rows": trace_rows,
                "slave_rows": 0,
                "constraint_applied_before_global_matrix_insertion": False,
            },
        )

    if int(index_map.size_global) != int(
        mpc.function_space.dofmap.index_map.size_global
    ):
        raise ValueError("MPC and assembly spaces have different global sizes")
    local_slaves = np.unique(np.asarray(mpc.slaves, dtype=np.int64))
    owned_local_slaves = local_slaves[
        (local_slaves >= 0) & (local_slaves < int(index_map.size_local))
    ]
    owned_slave_original = np.asarray(
        index_map.local_to_global(owned_local_slaves.astype(np.int32)),
        dtype=np.int64,
    )
    non_trace_slaves = [
        int(value)
        for value in owned_slave_original
        if int(value) not in original_to_trace
    ]
    if non_trace_slaves:
        raise ValueError(
            "assembly-time trace condensation found non-trace MPC slaves: "
            f"{non_trace_slaves[:8]}"
        )
    slave_packets = comm.allgather(owned_slave_original)
    global_slave_original = {int(value) for packet in slave_packets for value in packet}
    owned_active = owned_trace[
        ~np.isin(
            owned_trace,
            np.asarray(sorted(global_slave_original), dtype=PETSc.IntType),
            assume_unique=False,
        )
    ]
    active_counts = comm.allgather(int(len(owned_active)))
    active_start = int(sum(active_counts[: comm.rank]))
    active_packets = comm.allgather(
        (
            np.asarray(owned_active, dtype=np.int64),
            np.arange(
                active_start,
                active_start + len(owned_active),
                dtype=np.int64,
            ),
        )
    )
    original_to_active: dict[int, int] = {}
    for originals, active in active_packets:
        original_to_active.update(
            (int(original), int(reduced))
            for original, reduced in zip(originals, active, strict=True)
        )
    active_rows = int(sum(active_counts))
    slave_rows = int(len(global_slave_original))
    if active_rows + slave_rows != trace_rows:
        raise RuntimeError("trace MPC row counts do not close")

    mpc_index_map = mpc.function_space.dofmap.index_map
    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    owned_constraint_rows: list[tuple[int, np.ndarray, np.ndarray]] = []
    for local_slave, original_slave in zip(
        owned_local_slaves,
        owned_slave_original,
        strict=True,
    ):
        masters_local = np.asarray(
            mpc.masters.links(int(local_slave)),
            dtype=np.int32,
        )
        start = int(offsets[int(local_slave)])
        stop = int(offsets[int(local_slave) + 1])
        row_coefficients = coefficients[start:stop]
        if len(masters_local) != len(row_coefficients):
            raise RuntimeError("MPC master and coefficient counts disagree")
        masters_original = np.asarray(
            mpc_index_map.local_to_global(masters_local),
            dtype=np.int64,
        )
        owned_constraint_rows.append(
            (
                int(original_slave),
                masters_original,
                row_coefficients.copy(),
            )
        )
    constraint_packets = comm.allgather(owned_constraint_rows)
    expansion: dict[int, tuple[np.ndarray, np.ndarray]] = {
        int(original): (
            _idx([original_to_active[int(original)]]),
            np.asarray([1.0], dtype=np.complex128),
        )
        for original in original_to_active
    }
    maximum_masters = 0
    for packet in constraint_packets:
        for slave, masters, row_coefficients in packet:
            if slave in expansion:
                raise RuntimeError("duplicate or active MPC slave trace row")
            if any(int(master) in global_slave_original for master in masters):
                raise NotImplementedError(
                    "assembly-time condensation does not accept chained MPC rows"
                )
            missing_masters = [
                int(master)
                for master in masters
                if int(master) not in original_to_active
            ]
            if missing_masters:
                raise ValueError(
                    f"MPC trace row references non-trace masters: {missing_masters[:8]}"
                )
            active_ids = _idx(original_to_active[int(master)] for master in masters)
            expansion[int(slave)] = (
                active_ids,
                np.asarray(row_coefficients, dtype=np.complex128),
            )
            maximum_masters = max(maximum_masters, len(active_ids))
    missing_expansion = set(original_to_trace) - set(expansion)
    if missing_expansion:
        raise RuntimeError(
            f"trace constraint expansion is incomplete: {sorted(missing_expansion)[:8]}"
        )
    return TraceConstraintMap(
        owned_active_original_dofs=owned_active,
        original_to_active=original_to_active,
        expansion_by_original=expansion,
        full_trace_rows=trace_rows,
        active_rows=active_rows,
        slave_rows=slave_rows,
        owned_active_range=(active_start, active_start + len(owned_active)),
        build_audit={
            "schema_version": "task035b.trace-constraint-map.v1",
            "status": "exact_mpc_trace_expansion_built",
            "full_trace_rows": trace_rows,
            "active_rows": active_rows,
            "slave_rows": slave_rows,
            "maximum_masters_per_slave": maximum_masters,
            "constraint_applied_before_global_matrix_insertion": True,
            "embedded_identity_slave_rows_allocated": False,
        },
    )


def _cell_trace_expansion(
    trace_original: np.ndarray,
    constraints: TraceConstraintMap,
) -> tuple[np.ndarray, sparse.csr_matrix, bool]:
    """Return unique active columns and the sparse local expansion matrix."""

    if isinstance(constraints.expansion_by_original, _CompactTraceExpansionMapping):
        return constraints.expansion_by_original.expand_rows(
            np.asarray(trace_original, dtype=PETSc.IntType)
        )

    active_blocks = [
        constraints.expansion_by_original[int(original)] for original in trace_original
    ]
    unique_active = _idx(
        sorted({int(active) for ids, _coefficients in active_blocks for active in ids})
    )
    local_column = {
        int(active): position for position, active in enumerate(unique_active)
    }
    rows: list[int] = []
    columns: list[int] = []
    values: list[complex] = []
    identity = len(unique_active) == len(trace_original)
    for row, (ids, coefficients) in enumerate(active_blocks):
        if len(ids) != 1 or complex(coefficients[0]) != 1.0:
            identity = False
        for active, coefficient in zip(ids, coefficients, strict=True):
            column = local_column[int(active)]
            rows.append(row)
            columns.append(column)
            values.append(complex(coefficient))
            if identity and column != row:
                identity = False
    expansion = sparse.csr_matrix(
        (
            np.asarray(values, dtype=np.complex128),
            (np.asarray(rows, dtype=np.int32), np.asarray(columns, dtype=np.int32)),
        ),
        shape=(len(trace_original), len(unique_active)),
    )
    return unique_active, expansion, identity


def _readonly_array_reference(values: np.ndarray) -> np.ndarray:
    """Return a non-writable view without copying an owner-cached array."""

    view = np.asarray(values).view()
    view.flags.writeable = False
    return view


def iter_selected_volume_audit_cells(
    condensed: AssemblyTimeCondensedSystem,
    selected_active_rows: Any | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield owner-backed volume maps for cells touching selected active rows.

    ``cell_index`` is the index in the owner's locally owned cell-map tuple.
    Selecting an active row includes every cell whose exact trace expansion
    references it, including cells that contribute through an MPC slave.
    The cached ``T=-J K^-1``, ``R=-K^-1 G``, ``S`` and ``LU`` arrays are
    exposed as read-only views and are never copied or rebuilt here.
    """

    selected: frozenset[int] | None = None
    if selected_active_rows is not None:
        rows = np.asarray(selected_active_rows)
        if rows.ndim != 1:
            raise ValueError("selected_active_rows must be a one-dimensional integer sequence")
        if rows.size and rows.dtype.kind not in "iu":
            raise ValueError("selected_active_rows must contain only integer active rows")
        selected_values = tuple(int(row) for row in rows)
        if any(row < 0 or row >= int(condensed.active_rows) for row in selected_values):
            raise ValueError(
                f"selected_active_rows must lie in [0, {int(condensed.active_rows)})"
            )
        selected = frozenset(selected_values)

    schur_by_class = condensed.retained_local_schur_by_class
    if schur_by_class is None:
        raise RuntimeError(
            "volume audit requires the owner's retained local Schur cache; "
            "build with retain_local_schur_for_matrix_free=True"
        )

    for cell_index, cell in enumerate(condensed.cell_recovery_maps):
        active_ids, expansion, _identity = _cell_trace_expansion(
            cell.trace_original_dofs,
            condensed.trace_constraints,
        )
        if selected is not None and not any(
            np.any(active_ids == active_id) for active_id in selected
        ):
            continue

        class_key = cell.class_key
        try:
            T = condensed.trace_from_interior_rhs_by_class[class_key]
            R = condensed.interior_from_trace_by_class[class_key]
            S = schur_by_class[class_key]
            lu, pivots = condensed.interior_lu_by_class[class_key]
        except KeyError as exc:
            raise RuntimeError(
                f"volume audit owner cache is missing {exc.args[0]!r} "
                f"for cell {cell_index} class {class_key!r}"
            ) from exc

        expansion.data.flags.writeable = False
        expansion.indices.flags.writeable = False
        expansion.indptr.flags.writeable = False
        yield {
            "cell_index": cell_index,
            "class_key": class_key,
            "interior_original_dofs": _readonly_array_reference(
                cell.interior_original_dofs
            ),
            "trace_original_dofs": _readonly_array_reference(
                cell.trace_original_dofs
            ),
            "active_ids": _readonly_array_reference(active_ids),
            "E": expansion,
            "T": _readonly_array_reference(T),
            "R": _readonly_array_reference(R),
            "S": _readonly_array_reference(S),
            "LU": (
                _readonly_array_reference(lu),
                _readonly_array_reference(pivots),
            ),
        }


def _collective_preallocation_error(
    errors: list[str | None],
    *,
    context: str,
) -> None:
    """Raise the same preallocation validation error on every MPI rank."""

    if not any(error is not None for error in errors):
        return
    error_class = (
        ValueError
        if all(error is None or error.startswith("ValueError:") for error in errors)
        else TypeError
        if all(error is None or error.startswith("TypeError:") for error in errors)
        else RuntimeError
    )
    raise error_class(
        f"{context}: "
        + "; ".join(
            f"rank {rank}: {error}"
            for rank, error in enumerate(errors)
            if error is not None
        )
    )


def _distributed_trace_preallocation(
    comm,
    cell_active_ids: tuple[np.ndarray, ...],
    *,
    active_counts: tuple[int, ...],
    appended_global_rows: int,
    appended_support_owned_cell_groups: tuple[np.ndarray, ...],
    appended_support_group_by_row: tuple[int, ...],
    dense_appended_block: bool = False,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Build exact base and support-safe appended AIJ preallocation."""

    local_validation_error = None
    local_contract = None
    try:
        normalized_active_counts = tuple(int(count) for count in active_counts)
        normalized_appended_rows = int(appended_global_rows)
        normalized_group_by_row = tuple(
            int(group) for group in appended_support_group_by_row
        )
        normalized_dense_appended_block = bool(dense_appended_block)
        if len(normalized_active_counts) != comm.size:
            raise ValueError("active row counts do not match the MPI communicator")
        if any(count < 0 for count in normalized_active_counts):
            raise ValueError("active row counts must be nonnegative")
        if normalized_appended_rows < 0:
            raise ValueError("appended row count must be nonnegative")
        active_rows_for_validation = int(sum(normalized_active_counts))
        for ids in cell_active_ids:
            active = np.asarray(ids, dtype=np.int64)
            if len(active) == 0:
                raise ValueError("a cell has no active constrained trace rows")
            if int(active.min()) < 0 or int(active.max()) >= active_rows_for_validation:
                raise ValueError("a cell contains an out-of-range active trace row")
        if normalized_appended_rows == 0:
            if appended_support_owned_cell_groups or normalized_group_by_row:
                raise ValueError("appended support was provided without appended rows")
        elif (
            len(normalized_group_by_row) != normalized_appended_rows
            or not appended_support_owned_cell_groups
        ):
            raise ValueError("every appended row requires an explicit support group")
        group_count = len(appended_support_owned_cell_groups)
        invalid_groups = [
            group
            for group in normalized_group_by_row
            if group < 0 or group >= group_count
        ]
        if invalid_groups:
            raise ValueError(
                f"invalid appended-row support groups {invalid_groups[:8]}"
            )
        for local_cells in appended_support_owned_cell_groups:
            cells = np.asarray(local_cells, dtype=np.int64)
            if len(cells) and (
                int(cells.min()) < 0 or int(cells.max()) >= len(cell_active_ids)
            ):
                raise ValueError("appended support group contains a non-owned cell")
        local_contract = (
            normalized_active_counts,
            normalized_appended_rows,
            group_count,
            normalized_group_by_row,
            normalized_dense_appended_block,
        )
    except Exception as error:
        local_validation_error = f"{type(error).__name__}: {error}"
    validation_packets = comm.allgather((local_validation_error, local_contract))
    _collective_preallocation_error(
        [packet[0] for packet in validation_packets],
        context="trace preallocation input validation failed",
    )
    contracts = [packet[1] for packet in validation_packets]
    if any(contract != contracts[0] for contract in contracts[1:]):
        raise RuntimeError("trace preallocation contract differs across MPI ranks")
    assert local_contract is not None
    (
        normalized_active_counts,
        normalized_appended_rows,
        _group_count,
        normalized_group_by_row,
        normalized_dense_appended_block,
    ) = local_contract
    active_offsets = np.concatenate(
        (
            np.asarray([0], dtype=np.int64),
            np.cumsum(np.asarray(normalized_active_counts, dtype=np.int64)),
        )
    )
    active_rows = int(active_offsets[-1])
    local_active_start = int(active_offsets[comm.rank])
    local_active_end = int(active_offsets[comm.rank + 1])
    local_active_rows = local_active_end - local_active_start
    local_appended_rows = normalized_appended_rows if comm.rank == comm.size - 1 else 0
    local_rows = local_active_rows + local_appended_rows
    local_end = local_active_start + local_rows

    send_packets: list[list[np.ndarray]] = [[] for _rank in range(comm.size)]
    for ids in cell_active_ids:
        active = np.asarray(ids, dtype=PETSc.IntType)
        owners = np.searchsorted(
            active_offsets[1:],
            np.asarray(active, dtype=np.int64),
            side="right",
        )
        for owner in np.unique(owners):
            send_packets[int(owner)].append(active)
    received_packets = comm.alltoall(send_packets)
    incident: list[list[np.ndarray]] = [[] for _row in range(local_active_rows)]
    received_cell_graphs = 0
    local_receive_error = None
    try:
        for packet in received_packets:
            for ids in packet:
                active = np.asarray(ids, dtype=PETSc.IntType)
                local_mask = (active >= local_active_start) & (
                    active < local_active_end
                )
                for row in active[local_mask]:
                    incident[int(row) - local_active_start].append(active)
                received_cell_graphs += 1
    except Exception as error:
        local_receive_error = f"{type(error).__name__}: {error}"
    _collective_preallocation_error(
        comm.allgather(local_receive_error),
        context="trace preallocation graph exchange failed",
    )

    local_supports: list[np.ndarray] = []
    local_support_error = None
    try:
        for local_cells in appended_support_owned_cell_groups:
            cells = np.asarray(local_cells, dtype=np.int64)
            local_parts = [
                np.asarray(
                    cell_active_ids[int(cell)],
                    dtype=PETSc.IntType,
                )
                for cell in cells
            ]
            local_supports.append(
                np.unique(np.concatenate(local_parts)).astype(
                    PETSc.IntType,
                    copy=False,
                )
                if local_parts
                else np.empty(0, dtype=PETSc.IntType)
            )
    except Exception as error:
        local_support_error = f"{type(error).__name__}: {error}"
    _collective_preallocation_error(
        comm.allgather(local_support_error),
        context="trace preallocation local support construction failed",
    )

    support_groups: list[np.ndarray] = []
    for local_support in local_supports:
        support_packets = comm.allgather(local_support)
        nonempty = [packet for packet in support_packets if len(packet)]
        support = (
            np.unique(np.concatenate(nonempty)).astype(
                PETSc.IntType,
                copy=False,
            )
            if nonempty
            else np.empty(0, dtype=PETSc.IntType)
        )
        if normalized_appended_rows and len(support) == 0:
            raise ValueError("an appended-row support group is empty")
        support_groups.append(support)

    appended_columns_by_local_active: list[list[np.ndarray]] = [
        [] for _row in range(local_active_rows)
    ]
    group_rows: list[np.ndarray] = []
    row_groups = np.asarray(
        normalized_group_by_row,
        dtype=np.int64,
    )
    for group_index, support in enumerate(support_groups):
        appended_indices = np.flatnonzero(row_groups == group_index)
        appended_columns = (active_rows + appended_indices).astype(PETSc.IntType)
        group_rows.append(appended_columns)
        local_support = support[
            (support >= local_active_start) & (support < local_active_end)
        ]
        for row in local_support:
            appended_columns_by_local_active[int(row) - local_active_start].append(
                appended_columns
            )

    diagonal_nnz = np.zeros(local_rows, dtype=PETSc.IntType)
    off_diagonal_nnz = np.zeros(local_rows, dtype=PETSc.IntType)
    structural_nnz_local = 0
    local_row_error = None
    try:
        for local_row in range(local_active_rows):
            if not incident[local_row]:
                raise RuntimeError(
                    "an owned active trace row has no incident cell graph"
                )
            parts = [
                *incident[local_row],
                *appended_columns_by_local_active[local_row],
            ]
            columns = np.unique(np.concatenate(parts))
            diagonal = int(
                np.count_nonzero(
                    (columns >= local_active_start) & (columns < local_end)
                )
            )
            diagonal_nnz[local_row] = diagonal
            off_diagonal_nnz[local_row] = len(columns) - diagonal
            structural_nnz_local += len(columns)

        if local_appended_rows:
            for appended_index in range(normalized_appended_rows):
                local_row = local_active_rows + appended_index
                group = normalized_group_by_row[appended_index]
                appended_columns = (
                    np.arange(
                        active_rows,
                        active_rows + normalized_appended_rows,
                        dtype=PETSc.IntType,
                    )
                    if normalized_dense_appended_block
                    else np.asarray(
                        [active_rows + appended_index],
                        dtype=PETSc.IntType,
                    )
                )
                columns = np.unique(
                    np.concatenate(
                        (
                            support_groups[group],
                            appended_columns,
                        )
                    )
                )
                diagonal = int(
                    np.count_nonzero(
                        (columns >= local_active_start) & (columns < local_end)
                    )
                )
                diagonal_nnz[local_row] = diagonal
                off_diagonal_nnz[local_row] = len(columns) - diagonal
                structural_nnz_local += len(columns)
    except Exception as error:
        local_row_error = f"{type(error).__name__}: {error}"
    _collective_preallocation_error(
        comm.allgather(local_row_error),
        context="trace preallocation row construction failed",
    )

    preallocated_nnz = int(comm.allreduce(structural_nnz_local, op=MPI.SUM))
    return (
        diagonal_nnz,
        off_diagonal_nnz,
        {
            "schema_version": "task035b.exact-trace-preallocation.v1",
            "policy": (
                "distributed_exact_constrained_cell_graph_plus_"
                "support_safe_appended_upper_bound"
            ),
            "base_graph_preallocation": "exact",
            "appended_graph_preallocation": (
                "support_safe_upper_bound"
                if normalized_appended_rows
                else "not_applicable"
            ),
            "active_rows": active_rows,
            "appended_rows": normalized_appended_rows,
            "local_row_count": local_rows,
            "received_cell_graph_count": received_cell_graphs,
            "preallocated_structural_nnz": preallocated_nnz,
            "maximum_diagonal_nnz": int(
                comm.allreduce(
                    int(diagonal_nnz.max(initial=0)),
                    op=MPI.MAX,
                )
            ),
            "maximum_off_diagonal_nnz": int(
                comm.allreduce(
                    int(off_diagonal_nnz.max(initial=0)),
                    op=MPI.MAX,
                )
            ),
            "appended_support_group_count": len(support_groups),
            "appended_support_active_row_counts": [
                int(len(support)) for support in support_groups
            ],
            "appended_rows_per_support_group": [int(len(rows)) for rows in group_rows],
            "dense_appended_block": normalized_dense_appended_block,
            "new_nonzero_allocation_error_enabled": True,
            "ordinary_default_changed": False,
        },
    )


def _constrain_local_schur(
    schur: np.ndarray,
    expansion: sparse.csr_matrix,
    identity: bool,
) -> np.ndarray:
    if identity:
        return schur
    left = expansion.conjugate().transpose().dot(schur)
    # The final transpose is generally a non-contiguous view.  petsc4py's
    # dense setValues path requires a C-contiguous row-major buffer.
    return np.ascontiguousarray(expansion.transpose().dot(left.transpose()).transpose())


def _canonical_axis_aligned_coordinates(
    mesh,
    cell: int,
    *,
    tolerance: float,
    preserve_exact_geometry: bool = False,
) -> tuple[np.ndarray, tuple[float, float, float]]:
    geometry_dofs = np.asarray(mesh.geometry.dofmap[cell], dtype=np.int32)
    coordinates = np.asarray(
        mesh.geometry.x[geometry_dofs],
        dtype=np.float64,
    )
    if coordinates.shape != (8, 3):
        raise ValueError(
            "assembly-time condensation requires first-order hexahedral geometry"
        )
    lower = coordinates.min(axis=0)
    upper = coordinates.max(axis=0)
    widths = upper - lower
    if np.any(widths <= tolerance):
        raise ValueError("hexahedral cell has a nonpositive axis width")
    canonical = coordinates - lower
    for axis in range(3):
        distance_to_lower = np.abs(canonical[:, axis])
        distance_to_upper = np.abs(canonical[:, axis] - widths[axis])
        lower_mask = distance_to_lower <= tolerance
        upper_mask = distance_to_upper <= tolerance
        if not np.all(lower_mask | upper_mask):
            raise ValueError(
                "assembly-time condensation requires axis-aligned affine hexahedra"
            )
        canonical[lower_mask, axis] = 0.0
        canonical[upper_mask, axis] = widths[axis]
    vertices = {
        tuple(int(value > 0.5 * widths[axis]) for axis, value in enumerate(point))
        for point in canonical
    }
    if len(vertices) != 8:
        raise ValueError("hexahedral geometry does not contain all box vertices")
    geometry_widths = tuple(float(value) for value in widths)
    if not preserve_exact_geometry:
        # Preserve the historical grouping for existing profiles.  Task40's
        # physical A6 cache opts into exact mesh widths so its local tensors
        # represent the same coordinates as the native assembled operator.
        geometry_widths = tuple(
            float(np.round(value, 12)) for value in geometry_widths
        )
        for axis, width in enumerate(geometry_widths):
            canonical[canonical[:, axis] != 0.0, axis] = width
    return np.ascontiguousarray(canonical.ravel()), geometry_widths


def _mesh_actual_exact_coordinates(mesh, cell: int, *, tolerance: float) -> tuple[np.ndarray, tuple[float, float, float]]:
    """Return the untouched mesh coordinate DoFs for one affine box cell."""

    geometry_dofs = np.asarray(mesh.geometry.dofmap[cell], dtype=np.int32)
    points = np.asarray(mesh.geometry.x[geometry_dofs], dtype=np.float64)
    if points.shape != (8, 3):
        raise ValueError(
            "mesh_actual_exact requires first-order hexahedral coordinate DoFs"
        )
    # Reuse only the established geometric validity check.  Its translated and
    # endpoint-normalized coordinates are deliberately discarded here.
    _canonical, widths = _canonical_axis_aligned_coordinates(
        mesh, cell, tolerance=tolerance, preserve_exact_geometry=True
    )
    return np.ascontiguousarray(points), widths


def _mesh_actual_form_identity(compiled_form, element, kernels: Mapping[int, Any]) -> tuple[str, str, str]:
    """Bind exact keys to the compiled kernel, material code, and FE layout."""

    ffi = compiled_form.module.ffi
    signature = ffi.string(compiled_form.ufcx_form.signature).decode("ascii")
    module_path = getattr(compiled_form.module, "__file__", None)
    module_sha = None
    if module_path and Path(module_path).is_file():
        digest = hashlib.sha256()
        with Path(module_path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        module_sha = digest.hexdigest()
    kernel_identity = {
        "ufcx_signature": signature,
        "module_sha256": module_sha,
        "integral_ids": [int(key) for key in sorted(kernels)],
        "integral_kernel_counts": [
            [int(key), _kernel_count(dict(kernels), int(key))]
            for key in sorted(kernels)
        ],
        "dtype": str(np.dtype(compiled_form.dtype)),
    }
    basix = element.basix_element
    layout_identity = {
        "element_hash": int(basix.hash()),
        "space_dimension": int(element.space_dimension),
        "entity_dofs": [
            [list(map(int, entity)) for entity in dimension]
            for dimension in basix.entity_dofs
        ],
    }
    # In this Task41 form, material constants are compiled into the cell
    # kernels; the integral tag selects the material branch.  The module hash
    # and UFL signature therefore bind those coefficients along with the tag.
    kernel_json = json.dumps(kernel_identity, sort_keys=True, separators=(",", ":"))
    layout_json = json.dumps(layout_identity, sort_keys=True, separators=(",", ":"))
    return (
        hashlib.sha256(kernel_json.encode("utf-8")).hexdigest(),
        hashlib.sha256(layout_json.encode("utf-8")).hexdigest(),
        signature,
    )


def _raw_tensor_evaluator_cache_identity(evaluator: Any) -> str:
    """Return a source-bound cache identity, with legacy fallback for other evaluators."""

    return str(getattr(evaluator, "cache_identity", evaluator.identity))


def _mesh_actual_raw_key(
    compiled_form,
    element,
    kernels: Mapping[int, Any],
    *,
    tag: int,
    coordinates: np.ndarray,
    material_identity: Mapping[str, Any] | None,
    form_identity: tuple[str, str, str] | None = None,
    material_sha256: str | None = None,
    raw_tensor_evaluator_identity: str | None = None,
) -> tuple[tuple[Any, ...], bytes]:
    """Construct a collision-checked identity for unmodified coordinate bytes."""

    coordinate_array = np.ascontiguousarray(coordinates, dtype=np.float64)
    coordinate_bytes = memoryview(coordinate_array).cast("B").tobytes()
    kernel_sha, layout_sha, signature = form_identity or _mesh_actual_form_identity(
        compiled_form, element, kernels
    )
    if material_sha256 is None:
        material_payload = {
            "cell_tag": int(tag),
            "compiled_kernel_sha256": kernel_sha,
            "ufcx_signature": signature,
            "explicit_material_identity": dict(material_identity or {}),
        }
        if raw_tensor_evaluator_identity is not None:
            material_payload["raw_tensor_evaluator_identity"] = (
                raw_tensor_evaluator_identity
            )
        material_json = json.dumps(
            material_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        material_sha256 = hashlib.sha256(material_json.encode("utf-8")).hexdigest()
    coordinate_sha = hashlib.sha256(coordinate_bytes).hexdigest()
    key = (
        "mesh_actual_exact",
        int(tag),
        material_sha256,
        layout_sha,
        tuple(int(value) for value in coordinate_array.shape),
        coordinate_array.dtype.str,
        coordinate_sha,
    )
    return key, coordinate_bytes


def _mesh_actual_material_sha256(
    form_identity: tuple[str, str, str],
    *,
    tag: int,
    material_identity: Mapping[str, Any] | None,
    raw_tensor_evaluator_identity: str | None = None,
) -> str:
    kernel_sha, _layout_sha, signature = form_identity
    payload = {
        "cell_tag": int(tag),
        "compiled_kernel_sha256": kernel_sha,
        "ufcx_signature": signature,
        "explicit_material_identity": dict(material_identity or {}),
    }
    if raw_tensor_evaluator_identity is not None:
        payload["raw_tensor_evaluator_identity"] = raw_tensor_evaluator_identity
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def assembly_time_geometry_class_counts(
    mesh,
    cell_tags,
    *,
    tolerance: float = 1.0e-11,
    preserve_exact_geometry: bool = False,
    geometry_policy: str = "canonical",
    compiled_form: Any | None = None,
    function_space: Any | None = None,
    geometry_material_identity_by_tag: Mapping[int, Mapping[str, Any]] | None = None,
) -> dict[str, int]:
    """Count global raw/oriented cache keys without constructing local tensors."""

    comm = mesh.comm
    tdim = int(mesh.topology.dim)
    owned_cells = int(mesh.topology.index_map(tdim).size_local)
    tags = _cell_tag_array(cell_tags, owned_cells)
    mesh.topology.create_entity_permutations()
    permutations = mesh.topology.get_cell_permutation_info()
    local_raw_classes = set()
    local_oriented_classes = set()
    if geometry_policy not in {"canonical", "mesh_actual_exact"}:
        raise ValueError(f"unknown assembly-time geometry policy {geometry_policy!r}")
    if geometry_policy == "mesh_actual_exact" and allocation_gate is None:
        raise ValueError("mesh_actual_exact requires metadata and continuation allocation gates")
    if geometry_policy == "mesh_actual_exact" and raw_tensor_evaluator is not None:
        raise ValueError("mesh_actual_exact uses the original compiled rank-2 kernel directly")
    if geometry_policy == "mesh_actual_exact" and materialize_global_matrix:
        raise ValueError("mesh_actual_exact is restricted to the production matrix-free action route")
    if geometry_policy == "mesh_actual_exact" and (
        compiled_form is None or function_space is None
    ):
        raise ValueError("mesh_actual_exact census requires the compiled form and function space")
    exact_coordinate_bytes: dict[tuple[Any, ...], bytes] = {}
    kernels = (
        _cell_integral_kernels(compiled_form)
        if geometry_policy == "mesh_actual_exact"
        else None
    )
    exact_form_identity = (
        _mesh_actual_form_identity(compiled_form, function_space.element, kernels)
        if geometry_policy == "mesh_actual_exact"
        else None
    )
    exact_material_hashes: dict[int, str] = {}
    for cell in range(owned_cells):
        if geometry_policy == "mesh_actual_exact":
            coordinates, _widths = _mesh_actual_exact_coordinates(
                mesh, cell, tolerance=tolerance
            )
            tag = int(tags[cell])
            if tag not in exact_material_hashes:
                exact_material_hashes[tag] = _mesh_actual_material_sha256(
                    exact_form_identity,
                    tag=tag,
                    material_identity=(geometry_material_identity_by_tag or {}).get(tag),
                )
            raw_key, coordinate_bytes = _mesh_actual_raw_key(
                compiled_form,
                function_space.element,
                kernels,
                tag=tag,
                coordinates=coordinates,
                material_identity=(geometry_material_identity_by_tag or {}).get(tag),
                form_identity=exact_form_identity,
                material_sha256=exact_material_hashes[tag],
            )
            previous_bytes = exact_coordinate_bytes.get(raw_key)
            if previous_bytes is not None and previous_bytes != coordinate_bytes:
                raise RuntimeError("mesh_actual_exact coordinate digest collision detected")
            exact_coordinate_bytes[raw_key] = coordinate_bytes
        else:
            _coordinates, widths = _canonical_axis_aligned_coordinates(
                mesh,
                cell,
                tolerance=tolerance,
                preserve_exact_geometry=preserve_exact_geometry,
            )
            raw_key = (int(tags[cell]), *widths)
        local_raw_classes.add(raw_key)
        local_oriented_classes.add(
            (raw_key, int(permutations[cell]))
        )
    packets = comm.allgather(
        (tuple(local_raw_classes), tuple(local_oriented_classes))
    )
    raw_classes = {key for raw_packet, _ in packets for key in raw_packet}
    oriented_classes = {
        key for _, oriented_packet in packets for key in oriented_packet
    }
    return {
        "raw_class_count": len(raw_classes),
        "oriented_class_count": len(oriented_classes),
        "local_raw_class_count": len(local_raw_classes),
        "local_oriented_class_count": len(local_oriented_classes),
    }


def _tabulate_cell_tensor(
    compiled_form,
    kernel,
    coordinates: np.ndarray,
    dimension: int,
) -> np.ndarray:
    tensor = np.zeros((dimension, dimension), dtype=np.complex128)
    ffi = compiled_form.module.ffi
    kernel(
        ffi.cast("double _Complex *", ffi.from_buffer(tensor)),
        ffi.NULL,
        ffi.NULL,
        ffi.cast("double *", ffi.from_buffer(coordinates)),
        ffi.NULL,
        ffi.NULL,
        ffi.NULL,
    )
    return tensor


def _tabulate_raw_tensor_class(
    compiled_form,
    kernels: dict[int, Any],
    coordinates: np.ndarray,
    *,
    tag: int,
    dimension: int,
) -> np.ndarray:
    tensor = np.zeros((dimension, dimension), dtype=np.complex128)
    default_kernels = kernels.get(-1)
    tagged_kernels = kernels.get(int(tag))
    if default_kernels is None and tagged_kernels is None:
        raise ValueError(f"compiled form has no default or tagged kernel for tag {tag}")
    if not isinstance(default_kernels, (tuple, list)):
        default_kernels = () if default_kernels is None else (default_kernels,)
    if not isinstance(tagged_kernels, (tuple, list)):
        tagged_kernels = () if tagged_kernels is None else (tagged_kernels,)
    for kernel in (*default_kernels, *tagged_kernels):
        tensor += _tabulate_cell_tensor(
            compiled_form,
            kernel,
            coordinates,
            dimension,
        )
    return tensor


def _kernel_count(kernels: dict[int, Any], integral_id: int) -> int:
    value = kernels.get(int(integral_id))
    if value is None:
        return 0
    return len(value) if isinstance(value, (tuple, list)) else 1


def _global_raw_tensor_cache(
    comm,
    local_class_coordinates: dict[tuple[Any, ...], np.ndarray],
    policy_forms: dict[
        str,
        tuple[Any, dict[int, Any], int],
    ],
    *,
    raw_tensor_evaluator: Callable[..., np.ndarray] | None = None,
) -> tuple[dict[tuple[Any, ...], np.ndarray], dict[str, Any], float]:
    """Evaluate each raw tensor class once globally, then broadcast it.

    Every rank participates in the deterministic class order.  Only ranks
    owning cells in a class retain its tensor after the broadcast.
    """

    local_policy_signature = {
        policy: {
            "dimension": int(dimension),
            "kernel_ids": tuple(sorted(int(key) for key in kernels)),
            "kernel_counts": tuple(
                (int(key), _kernel_count(kernels, int(key)))
                for key in sorted(kernels)
            ),
            "dtype": str(np.dtype(compiled_form.dtype)),
            "element_hash": int(
                compiled_form.function_spaces[0].element.basix_element.hash()
            ),
            "ufcx_form_signature": compiled_form.module.ffi.string(
                compiled_form.ufcx_form.signature
            ).decode("ascii"),
            "raw_tensor_evaluator": (
                None
                if raw_tensor_evaluator is None
                else {
                    "identity": str(raw_tensor_evaluator.identity),
                    "cache_identity": _raw_tensor_evaluator_cache_identity(
                        raw_tensor_evaluator
                    ),
                    "full_form_signature": str(
                        raw_tensor_evaluator.analysis_facts["full_form_signature"]
                    ),
                    "workspace_bytes_upper": int(
                        raw_tensor_evaluator.workspace_bytes_upper
                    ),
                }
            ),
        }
        for policy, (compiled_form, kernels, dimension) in policy_forms.items()
    }
    policy_signatures = comm.allgather(local_policy_signature)
    if any(signature != policy_signatures[0] for signature in policy_signatures[1:]):
        raise RuntimeError("raw tensor FFCx policy signatures differ across MPI ranks")
    if raw_tensor_evaluator is not None:
        compiled_form, kernels, _dimension = policy_forms["actual_space"]
        local_validation_error = None
        try:
            raw_tensor_evaluator.validate_compiled_form(compiled_form, kernels)
        except Exception as error:
            local_validation_error = f"{type(error).__name__}: {error}"
        validation_errors = comm.allgather(local_validation_error)
        if any(error is not None for error in validation_errors):
            raise RuntimeError(
                "p6 raw tensor candidate form validation failed: "
                + "; ".join(
                    f"rank {rank}: {error}"
                    for rank, error in enumerate(validation_errors)
                    if error is not None
                )
            )
    packets = comm.allgather(
        tuple(
            (key, np.asarray(coordinates, dtype=np.float64))
            for key, coordinates in local_class_coordinates.items()
        )
    )
    global_coordinates: dict[tuple[Any, ...], np.ndarray] = {}
    ranks_by_class: dict[tuple[Any, ...], list[int]] = {}
    for rank, packet in enumerate(packets):
        for key, coordinates in packet:
            canonical = np.asarray(coordinates, dtype=np.float64)
            previous = global_coordinates.get(key)
            if previous is not None and not np.array_equal(
                previous,
                canonical,
            ):
                raise RuntimeError(
                    "raw tensor class has inconsistent canonical geometry "
                    "across MPI ranks"
                )
            global_coordinates.setdefault(key, canonical)
            ranks_by_class.setdefault(key, []).append(rank)

    ordered_keys = sorted(global_coordinates)
    owner_loads = [0] * comm.size
    owner_by_class: dict[tuple[Any, ...], int] = {}
    for key in sorted(
        ordered_keys,
        key=lambda value: (
            -(
                int(policy_forms[str(value[0])][2]) ** 2
                * (
                    _kernel_count(policy_forms[str(value[0])][1], -1)
                    + _kernel_count(policy_forms[str(value[0])][1], int(value[1]))
                )
            ),
            value,
        ),
    ):
        owner = min(range(comm.size), key=lambda rank: (owner_loads[rank], rank))
        owner_by_class[key] = int(owner)
        owner_loads[owner] += int(policy_forms[str(key[0])][2]) ** 2 * (
            _kernel_count(policy_forms[str(key[0])][1], -1)
            + _kernel_count(policy_forms[str(key[0])][1], int(key[1]))
        )
    cache: dict[tuple[Any, ...], np.ndarray] = {}
    local_kernel_seconds = 0.0
    local_broadcast_seconds = 0.0
    local_evaluations = 0
    logical_broadcast_bytes = 0
    local_keys = set(local_class_coordinates)
    locally_evaluated: dict[tuple[Any, ...], np.ndarray] = {}
    local_kernel_error = None
    try:
        for key in ordered_keys:
            if comm.rank != owner_by_class[key]:
                continue
            policy = str(key[0])
            if policy not in policy_forms:
                raise RuntimeError(f"unknown raw tensor policy {policy!r}")
            compiled_form, kernels, dimension = policy_forms[policy]
            kernel_started = perf_counter()
            if raw_tensor_evaluator is None:
                locally_evaluated[key] = _tabulate_raw_tensor_class(
                    compiled_form,
                    kernels,
                    global_coordinates[key],
                    tag=int(key[1]),
                    dimension=int(dimension),
                )
            else:
                locally_evaluated[key] = raw_tensor_evaluator(
                    compiled_form,
                    kernels,
                    global_coordinates[key],
                    tag=int(key[1]),
                    dimension=int(dimension),
                )
            local_kernel_seconds += perf_counter() - kernel_started
            local_evaluations += 1
    except Exception as error:
        local_kernel_error = f"{type(error).__name__}: {error}"
    owner_sync_started = perf_counter()
    kernel_errors = comm.allgather(local_kernel_error)
    owner_sync_seconds = perf_counter() - owner_sync_started
    if any(error is not None for error in kernel_errors):
        raise RuntimeError(
            "global raw tensor evaluation failed before broadcast: "
            + "; ".join(
                f"rank {rank}: {error}"
                for rank, error in enumerate(kernel_errors)
                if error is not None
            )
        )

    for key in ordered_keys:
        policy = str(key[0])
        if policy not in policy_forms:
            raise RuntimeError(f"unknown raw tensor policy {policy!r}")
        _compiled_form, _kernels, dimension = policy_forms[policy]
        owner = owner_by_class[key]
        if comm.rank == owner:
            tensor = locally_evaluated.pop(key)
        else:
            tensor = np.empty(
                (int(dimension), int(dimension)),
                dtype=np.complex128,
            )
        broadcast_started = perf_counter()
        comm.Bcast(tensor, root=owner)
        local_broadcast_seconds += perf_counter() - broadcast_started
        logical_broadcast_bytes += int(tensor.nbytes * (comm.size - 1))
        if key in local_keys:
            cache[key] = tensor

    evaluation_count = int(comm.allreduce(local_evaluations, op=MPI.SUM))
    use_count = int(comm.allreduce(len(local_class_coordinates), op=MPI.SUM))
    unique_count = len(global_coordinates)
    if evaluation_count != unique_count:
        raise RuntimeError(
            "global raw tensor evaluation count does not match unique classes"
        )
    if set(cache) != local_keys:
        raise RuntimeError("global raw tensor cache is incomplete on this rank")
    evaluator_audit = None
    if raw_tensor_evaluator is not None:
        local_evaluator_facts = {
            "class_count": int(raw_tensor_evaluator.class_count),
            "class_seconds_total": float(
                getattr(raw_tensor_evaluator, "class_seconds_total", 0.0)
            ),
            "class_seconds_max": float(
                getattr(raw_tensor_evaluator, "class_seconds_max", 0.0)
            ),
        }
        evaluator_packets = comm.allgather(local_evaluator_facts)
        class_count_sum = int(
            sum(packet["class_count"] for packet in evaluator_packets)
        )
        class_seconds_total = float(
            sum(packet["class_seconds_total"] for packet in evaluator_packets)
        )
        class_seconds_max = float(
            max((packet["class_seconds_max"] for packet in evaluator_packets), default=0.0)
        )
        evaluator_audit = raw_tensor_evaluator.audit()
        evaluator_audit.update({
            "implementation": str(raw_tensor_evaluator.identity),
            "full_form_signature": str(
                raw_tensor_evaluator.analysis_facts["full_form_signature"]
            ),
            "ufcx_form_signature": str(
                raw_tensor_evaluator.expected_ufcx_signature
            ),
            "class_count_sum": class_count_sum,
            "class_seconds_summary": {
                "count": class_count_sum,
                "total": class_seconds_total,
                "max": class_seconds_max,
            },
            "workspace_bytes_upper": int(
                raw_tensor_evaluator.workspace_bytes_upper
            ),
            "literal_zero_default_integral_count": int(
                raw_tensor_evaluator.analysis_facts[
                    "literal_zero_default_integral_count"
                ]
            ),
            "ffcx_default_kernel_absent": bool(
                raw_tensor_evaluator.ffcx_default_kernel_absent
            ),
        })
    return (
        cache,
        {
            "raw_tensor_class_count_sum": evaluation_count,
            "raw_tensor_class_use_count_sum": use_count,
            "raw_tensor_class_count_global_unique": unique_count,
            "raw_tensor_global_owner_policy": (
                "deterministic_dimension_squared_greedy_all_mpi_ranks"
            ),
            "raw_tensor_owner_cost_loads": owner_loads,
            "raw_tensor_policy_signatures_identical": True,
            "raw_tensor_policy_signatures": policy_signatures[0],
            "raw_tensor_owner_evaluation_sync_seconds_max": float(
                comm.allreduce(owner_sync_seconds, op=MPI.MAX)
            ),
            "raw_tensor_cross_rank_dedup_active": bool(
                comm.size > 1 and use_count > unique_count
            ),
            "raw_tensor_class_owner_ranks": {
                repr(key): int(owner_by_class[key])
                for key in sorted(global_coordinates)
            },
            "raw_tensor_class_user_rank_counts": {
                repr(key): len(ranks_by_class[key])
                for key in sorted(global_coordinates)
            },
            "raw_tensor_classes": [
                {
                    "policy": str(key[0]),
                    "material_tag": int(key[1]),
                    "cell_widths": [float(value) for value in key[2:]],
                    "dimension": int(policy_forms[str(key[0])][2]),
                    "active_kernel_ids": [
                        kernel_id
                        for kernel_id in dict.fromkeys((-1, int(key[1])))
                        if kernel_id in policy_forms[str(key[0])][1]
                    ],
                    "owner_rank": int(owner_by_class[key]),
                    "consumer_rank_count": len(ranks_by_class[key]),
                    "tensor_bytes": int(
                        int(policy_forms[str(key[0])][2]) ** 2
                        * np.dtype(np.complex128).itemsize
                    ),
                    "canonical_coordinates_sha256": hashlib.sha256(
                        np.ascontiguousarray(
                            global_coordinates[key],
                            dtype=np.float64,
                        ).tobytes()
                    ).hexdigest(),
                }
                for key in ordered_keys
            ],
            "raw_tensor_evaluator": evaluator_audit,
            "raw_tensor_logical_broadcast_bytes": logical_broadcast_bytes,
            "raw_tensor_broadcast_seconds_max": float(
                comm.allreduce(local_broadcast_seconds, op=MPI.MAX)
            ),
        },
        local_kernel_seconds,
    )


def _orient_cell_tensor(element, tensor: np.ndarray, cell_info: np.ndarray) -> None:
    """Apply the same ``T A T^T`` transformation as DOLFINx assembly."""

    dimension = tensor.shape[0]
    if hasattr(element, "space_dimension"):
        element.T_apply(tensor.ravel(), cell_info, dimension)
    else:
        element.T_apply(
            tensor.ravel(),
            dimension,
            int(cell_info[0]),
        )
    transpose = np.ascontiguousarray(tensor.T)
    if hasattr(element, "space_dimension"):
        element.T_apply(transpose.ravel(), cell_info, dimension)
    else:
        element.T_apply(
            transpose.ravel(),
            dimension,
            int(cell_info[0]),
        )
    tensor[:] = transpose.T


def _unorient_cell_tensor(element, tensor: np.ndarray, cell_info: np.ndarray) -> None:
    """Invert the exact Basix congruence used by ``_orient_cell_tensor``.

    This is used only to compare a saved, already-oriented V4 actual block
    partition against the candidate's raw tensor.  It derives the transform
    from the bound element and cell permutation, then solves both sides with
    the same nonsingular transform; no coordinate or tensor normalization is
    introduced.
    """

    values = np.asarray(tensor)
    if values.ndim != 2 or values.shape[0] != values.shape[1]:
        raise ValueError("cell tensor orientation inverse requires a square matrix")
    dimension = int(values.shape[0])
    transform = np.eye(dimension, dtype=np.float64)
    info = np.asarray(cell_info, dtype=np.uint32)
    if hasattr(element, "space_dimension"):
        element.T_apply(transform.ravel(), info, dimension)
    else:
        element.T_apply(transform.ravel(), dimension, int(info[0]))
    transform_lu = lu_factor(transform, check_finite=True)
    left_solved = lu_solve(transform_lu, np.asarray(values, dtype=np.complex128))
    values[:] = lu_solve(transform_lu, left_solved.T).T


def _tabulate_volume_audit_path(
    compiled_form,
    kernels: dict[int, Any],
    element,
    coordinates: np.ndarray,
    *,
    tag: int,
    permutation: int,
    dimension: int,
    interior_positions: np.ndarray,
    trace_positions: np.ndarray,
) -> dict[str, np.ndarray]:
    """Tabulate one coordinate path through the existing rank-2 FFCx kernels."""

    raw_tensor = _tabulate_raw_tensor_class(
        compiled_form,
        kernels,
        coordinates,
        tag=tag,
        dimension=dimension,
    )
    oriented_tensor = raw_tensor.copy()
    _orient_cell_tensor(
        element,
        oriented_tensor,
        np.asarray([permutation], dtype=np.uint32),
    )
    return {
        "coordinates": np.ascontiguousarray(coordinates, dtype=np.float64),
        "raw_tensor": raw_tensor,
        "oriented_tensor": oriented_tensor,
        "K": oriented_tensor[np.ix_(interior_positions, interior_positions)],
        "G": oriented_tensor[np.ix_(interior_positions, trace_positions)],
        "J": oriented_tensor[np.ix_(trace_positions, interior_positions)],
        "L": oriented_tensor[np.ix_(trace_positions, trace_positions)],
    }


def tabulate_volume_audit_cell_geometry_pair(
    compiled_form,
    function_space,
    cell_tags,
    cell_index: int,
) -> dict[str, Any]:
    """Tabulate one cell with actual mesh and canonical coordinates.

    This helper has no dependency on a condensed owner, its LU factors, or any
    global volume cache. Both paths use the same compiled rank-2 FFCx kernels,
    orientation transform, and local DoF partition.
    """

    if isinstance(cell_index, (bool, np.bool_)) or not isinstance(
        cell_index, (int, np.integer)
    ):
        raise TypeError("cell_index must be an integer local cell index")
    cell_index = int(cell_index)
    mesh = function_space.mesh
    tdim = int(mesh.topology.dim)
    owned_cells = int(mesh.topology.index_map(tdim).size_local)
    if cell_index < 0 or cell_index >= owned_cells:
        raise IndexError(f"cell_index {cell_index} is outside [0, {owned_cells})")

    geometry_dofmap = np.asarray(mesh.geometry.dofmap, dtype=np.int32)
    geometry_coordinates = np.asarray(mesh.geometry.x, dtype=np.float64)
    if geometry_dofmap.ndim != 2 or geometry_dofmap.shape[0] < owned_cells:
        raise ValueError("mesh geometry DoF map does not cover owned cells")
    geometry_dofs = np.ascontiguousarray(geometry_dofmap[cell_index]).copy()
    actual_points = np.ascontiguousarray(geometry_coordinates[geometry_dofs]).copy()
    if actual_points.ndim != 2 or actual_points.shape[1] != 3:
        raise ValueError("actual cell coordinates must have shape (geometry_dofs, 3)")
    actual_coordinates = np.ascontiguousarray(actual_points.reshape(-1))
    canonical_coordinates, widths = _canonical_axis_aligned_coordinates(
        mesh,
        cell_index,
        tolerance=1.0e-11,
        preserve_exact_geometry=True,
    )
    canonical_points = np.ascontiguousarray(
        np.asarray(canonical_coordinates, dtype=np.float64).reshape(actual_points.shape)
    )
    canonical_coordinates = np.ascontiguousarray(canonical_points.reshape(-1))

    tag = int(_cell_tag_array(cell_tags, owned_cells)[cell_index])
    mesh.topology.create_entity_permutations()
    permutations = np.asarray(mesh.topology.get_cell_permutation_info(), dtype=np.uint32)
    if permutations.size < owned_cells:
        raise ValueError("cell permutation inventory does not cover owned cells")
    permutation = int(permutations[cell_index])

    element = function_space.element
    dimension = int(element.space_dimension)
    interior_positions = np.asarray(
        element.basix_element.entity_dofs[tdim][0], dtype=np.int32
    )
    trace_positions = np.setdiff1d(
        np.arange(dimension, dtype=np.int32), interior_positions
    )
    local_dofs = np.asarray(
        function_space.dofmap.cell_dofs(cell_index), dtype=np.int32
    )
    if local_dofs.shape != (dimension,):
        raise ValueError("cell DoF map does not match the finite-element dimension")
    original_dofs = np.asarray(
        function_space.dofmap.index_map.local_to_global(local_dofs), dtype=np.int64
    )
    kernels = _cell_integral_kernels(
        compiled_form,
        sum_duplicate_cell_integrals=True,
    )
    common = {
        "cell_index": cell_index,
        "cell_tag": tag,
        "class_key": (tag, *widths, permutation),
        "cell_widths": widths,
        "cell_permutation": permutation,
        "geometry_dofs": geometry_dofs,
        "actual_geometry_coordinates": actual_points,
        "canonical_geometry_coordinates": canonical_points,
        "local_dofs": local_dofs,
        "original_dofs": original_dofs,
        "interior_positions": interior_positions,
        "trace_positions": trace_positions,
        "interior_original_dofs": original_dofs[interior_positions],
        "trace_original_dofs": original_dofs[trace_positions],
        "integral_kernel_counts": {
            "default": _kernel_count(kernels, -1),
            "tagged": _kernel_count(kernels, tag),
        },
    }
    common["actual"] = _tabulate_volume_audit_path(
        compiled_form,
        kernels,
        element,
        actual_coordinates,
        tag=tag,
        permutation=permutation,
        dimension=dimension,
        interior_positions=interior_positions,
        trace_positions=trace_positions,
    )
    common["canonical"] = _tabulate_volume_audit_path(
        compiled_form,
        kernels,
        element,
        canonical_coordinates,
        tag=tag,
        permutation=permutation,
        dimension=dimension,
        interior_positions=interior_positions,
        trace_positions=trace_positions,
    )
    return common


def tabulate_volume_audit_cell(
    compiled_form,
    function_space,
    cell_tags,
    condensed: AssemblyTimeCondensedSystem,
    cell_index: int,
    *,
    geometry_policy: str | None = None,
) -> dict[str, Any]:
    """Tabulate and identify one cell's original oriented volume blocks.

    The full FFCx tensor is assembled from default/tag kernels, oriented, and
    sliced directly; no factorization or new FE object is constructed.
    """

    if isinstance(cell_index, (bool, np.bool_)) or not isinstance(
        cell_index, (int, np.integer)
    ):
        raise TypeError("cell_index must be an integer local cell index")
    cell_index = int(cell_index)
    mesh = function_space.mesh
    tdim = int(mesh.topology.dim)
    owned_cells = int(mesh.topology.index_map(tdim).size_local)
    if len(condensed.cell_recovery_maps) != owned_cells:
        raise ValueError("condensed owner cell maps do not match the FE owned-cell range")
    if cell_index < 0 or cell_index >= owned_cells:
        raise IndexError(f"cell_index {cell_index} is outside [0, {owned_cells})")
    cell_map = condensed.cell_recovery_maps[cell_index]
    tag = int(_cell_tag_array(cell_tags, owned_cells)[cell_index])
    owner_policy = str(condensed.build_audit.get("geometry_policy", "canonical"))
    selected_policy = owner_policy if geometry_policy is None else str(geometry_policy)
    if selected_policy not in {"canonical", "mesh_actual_exact"}:
        raise ValueError(f"unknown volume audit geometry policy {selected_policy!r}")
    if selected_policy == "mesh_actual_exact":
        coordinates, widths = _mesh_actual_exact_coordinates(
            mesh, cell_index, tolerance=1.0e-11
        )
    else:
        coordinates, widths = _canonical_axis_aligned_coordinates(
            mesh,
            cell_index,
            tolerance=1.0e-11,
            preserve_exact_geometry=True,
        )
    mesh.topology.create_entity_permutations()
    permutations = np.asarray(mesh.topology.get_cell_permutation_info(), dtype=np.uint32)
    permutation = int(permutations[cell_index])
    class_key = cell_map.class_key
    kernels = _cell_integral_kernels(
        compiled_form,
        sum_duplicate_cell_integrals=True,
    )
    if selected_policy == "mesh_actual_exact":
        form_identity = condensed.build_audit.get("geometry_form_identity")
        if form_identity is None:
            form_identity = _mesh_actual_form_identity(
                compiled_form, function_space.element, kernels
            )
        material_by_tag = condensed.build_audit.get(
            "geometry_material_identity_by_tag", {}
        )
        material_identity = material_by_tag.get(tag, material_by_tag.get(str(tag)))
        material_hashes = condensed.build_audit.get("geometry_material_sha256_by_tag", {})
        material_sha = material_hashes.get(tag, material_hashes.get(str(tag)))
        if material_sha is None:
            material_sha = _mesh_actual_material_sha256(
                form_identity,
                tag=tag,
                material_identity=material_identity,
                raw_tensor_evaluator_identity=condensed.build_audit.get(
                    "raw_tensor_evaluator_identity"
                ),
            )
        raw_key, _coordinate_bytes = _mesh_actual_raw_key(
            compiled_form,
            function_space.element,
            kernels,
            tag=tag,
            coordinates=coordinates,
            material_identity=material_identity,
            form_identity=form_identity,
            material_sha256=material_sha,
            raw_tensor_evaluator_identity=condensed.build_audit.get(
                "raw_tensor_evaluator_identity"
            ),
        )
        expected_class_key = (*raw_key, permutation)
    else:
        expected_class_key = (tag, *widths, permutation)
    if selected_policy == owner_policy and class_key != expected_class_key:
        raise ValueError(
            f"volume audit class identity mismatch for cell {cell_index}: "
            f"owner={class_key!r}, fresh={expected_class_key!r}"
        )

    element = function_space.element
    dimension = int(element.space_dimension)
    interior_positions = np.asarray(
        element.basix_element.entity_dofs[tdim][0], dtype=np.int32
    )
    trace_positions = np.setdiff1d(
        np.arange(dimension, dtype=np.int32), interior_positions
    )
    local_dofs = np.asarray(
        function_space.dofmap.cell_dofs(cell_index), dtype=np.int32
    )
    original_dofs = np.asarray(
        function_space.dofmap.index_map.local_to_global(local_dofs), dtype=np.int64
    )
    interior_original_dofs = original_dofs[interior_positions]
    trace_original_dofs = original_dofs[trace_positions]
    if (
        not np.array_equal(
            interior_original_dofs,
            np.asarray(cell_map.interior_original_dofs, dtype=np.int64),
        )
        or not np.array_equal(
            trace_original_dofs,
            np.asarray(cell_map.trace_original_dofs, dtype=np.int64),
        )
    ):
        raise ValueError(f"volume audit original-row identity mismatch for cell {cell_index}")

    path = _tabulate_volume_audit_path(
        compiled_form,
        kernels,
        element,
        coordinates,
        tag=tag,
        permutation=permutation,
        dimension=dimension,
        interior_positions=interior_positions,
        trace_positions=trace_positions,
    )
    raw_tensor = path["raw_tensor"]
    oriented_tensor = path["oriented_tensor"]
    K, G, J, L = (path[name] for name in ("K", "G", "J", "L"))

    arrays = {
        "canonical_coordinates": coordinates,
        "original_dofs": original_dofs,
        "interior_original_dofs": interior_original_dofs,
        "trace_original_dofs": trace_original_dofs,
        "raw_tensor": raw_tensor,
        "oriented_tensor": oriented_tensor,
        "K": K,
        "G": G,
        "J": J,
        "L": L,
    }
    hashes = {
        name: hashlib.sha256(
            memoryview(np.ascontiguousarray(values)).cast("B")
        ).hexdigest()
        for name, values in arrays.items()
    }

    return {
        "cell_index": cell_index,
        "cell_tag": tag,
        "class_key": class_key,
        "geometry_policy": selected_policy,
        "cell_widths": widths,
        "cell_permutation": permutation,
        "canonical_coordinates": coordinates,
        "local_dofs": local_dofs,
        "original_dofs": original_dofs,
        "interior_positions": interior_positions,
        "trace_positions": trace_positions,
        "interior_original_dofs": interior_original_dofs,
        "trace_original_dofs": trace_original_dofs,
        "K": K,
        "G": G,
        "J": J,
        "L": L,
        "hashes": hashes,
        "integral_kernel_counts": {
            "default": _kernel_count(kernels, -1),
            "tagged": _kernel_count(kernels, tag),
        },
    }


def _strict_local_lu(
    matrix: np.ndarray,
    *,
    residual_tolerance: float = 1.0e-11,
) -> tuple[tuple[np.ndarray, np.ndarray], float]:
    """Factor one cell-interior block with a small, explicit safety check.

    The check is deliberately a stability guard rather than a condition
    estimator: it turns LAPACK singularity warnings, non-finite factors, and
    a visibly defective reconstructed identity into a hard setup failure.
    The ordinary condensation path does not call this helper.
    """

    values = np.asarray(matrix, dtype=np.complex128)
    if not np.all(np.isfinite(values)):
        raise FloatingPointError("cell-interior tensor contains non-finite values")
    with warnings.catch_warnings():
        warnings.simplefilter("error", LinAlgWarning)
        factor = lu_factor(values, check_finite=True)
    lu, pivots = factor
    if not np.all(np.isfinite(lu)):
        raise FloatingPointError("cell-interior LU contains non-finite values")
    identity = np.eye(values.shape[0], dtype=np.complex128)
    reconstructed = lu_solve(factor, identity)
    defect = float(np.linalg.norm(values @ reconstructed - identity))
    scale = max(float(np.linalg.norm(values)) * float(np.linalg.norm(reconstructed)), 1.0)
    relative_defect = defect / scale
    if not np.isfinite(relative_defect) or relative_defect > float(residual_tolerance):
        raise np.linalg.LinAlgError(
            "cell-interior LU identity check failed: "
            f"relative defect {relative_defect:.3e} > {float(residual_tolerance):.3e}"
        )
    return (lu, pivots), relative_defect


def _retained_array_bytes(value: Any) -> int:
    """Count bytes in a retained NumPy array or a tuple of arrays."""

    if isinstance(value, np.ndarray):
        return int(value.nbytes)
    if isinstance(value, (tuple, list)):
        return int(sum(_retained_array_bytes(item) for item in value))
    return 0


def build_unconstrained_assembly_time_condensation(
    compiled_form,
    function_space,
    cell_tags,
    *,
    mpc=None,
    appended_global_rows: int = 0,
    appended_support_owned_cell_groups: tuple[np.ndarray, ...] = (),
    appended_support_group_by_row: tuple[int, ...] = (),
    dense_appended_block: bool = False,
    sum_duplicate_cell_integrals: bool = False,
    strict_local_checks: bool = False,
    defer_final_assembly: bool = False,
    retain_local_schur_for_matrix_free: bool = False,
    share_identity_cache: bool = False,
    materialize_global_matrix: bool = True,
    compact_action_only_maps: bool = False,
    geometry_tolerance: float = 1.0e-11,
    preserve_exact_geometry: bool = False,
    geometry_policy: str = "canonical",
    geometry_material_identity_by_tag: Mapping[int, Mapping[str, Any]] | None = None,
    required_prefix_cells: Sequence[int] = (),
    prefix_cell_validator: Callable[
        [int, np.ndarray, Mapping[str, np.ndarray], Mapping[str, Any]], Mapping[str, Any]
    ]
    | None = None,
    exact_cell_observer: Callable[
        [int, np.ndarray, Mapping[str, np.ndarray], Mapping[str, Any]], None
    ]
    | None = None,
    allocation_gate: Callable[[str, Mapping[str, Any]], None] | None = None,
    raw_tensor_evaluator: Callable[..., np.ndarray] | None = None,
) -> AssemblyTimeCondensedSystem:
    """Assemble only the independent H(curl) trace Schur matrix.

    When ``mpc`` is supplied, its trace constraints are applied to each local
    Schur tensor before insertion.  No full-trace matrix or embedded slave
    identity rows are allocated.

    ``retain_local_schur_for_matrix_free`` retains one readonly Schur array
    per local class for a later owner-computes action.  When
    ``share_identity_cache`` is true, the exact real identity used by the
    three recovery/projection roles is shared read-only across all local
    classes with the same interior shape.  The default keeps the historical
    per-class allocation.
    """

    if np.dtype(compiled_form.dtype) != np.dtype(np.complex128):
        raise TypeError("assembly-time condensation requires complex128")
    if geometry_policy not in {"canonical", "mesh_actual_exact"}:
        raise ValueError(f"unknown assembly-time geometry policy {geometry_policy!r}")
    required_prefix_cells = tuple(int(cell) for cell in required_prefix_cells)
    if (required_prefix_cells or prefix_cell_validator is not None) and geometry_policy != "mesh_actual_exact":
        raise ValueError("required exact-prefix cell checks need mesh_actual_exact geometry")
    if exact_cell_observer is not None and geometry_policy != "mesh_actual_exact":
        raise ValueError("exact-cell observer requires mesh_actual_exact geometry")
    if len(set(required_prefix_cells)) != len(required_prefix_cells):
        raise ValueError("required exact-prefix cell indices must be unique")
    if int(appended_global_rows) < 0:
        raise ValueError("appended_global_rows must be non-negative")
    materialize_global_matrix = bool(materialize_global_matrix)
    if not materialize_global_matrix and not retain_local_schur_for_matrix_free:
        raise ValueError(
            "action-only condensation requires retained local Schur classes"
        )
    if compact_action_only_maps and materialize_global_matrix:
        raise ValueError("compact_action_only_maps is restricted to action-only condensation")
    appended_global_rows = int(appended_global_rows)
    mesh = function_space.mesh
    comm = mesh.comm
    if geometry_policy == "mesh_actual_exact" and comm.size != 1:
        raise NotImplementedError("mesh_actual_exact is qualified only for the frozen MPI1 candidate")
    if geometry_policy == "mesh_actual_exact" and not share_identity_cache:
        raise ValueError("mesh_actual_exact requires the shared identity cache for capacity accounting")
    if geometry_policy == "mesh_actual_exact" and materialize_global_matrix:
        raise ValueError("mesh_actual_exact is restricted to the production matrix-free action route")
    if "hexahedron" not in str(mesh.basix_cell()).lower():
        raise NotImplementedError(
            "assembly-time condensation currently supports hexahedra only"
        )
    dofmap = function_space.dofmap
    if int(dofmap.index_map_bs) != 1:
        raise NotImplementedError(
            "assembly-time condensation requires scalar-blocked H(curl)"
        )
    started = perf_counter()
    tdim = mesh.topology.dim
    owned_cells = int(mesh.topology.index_map(tdim).size_local)
    tags = _cell_tag_array(cell_tags, owned_cells)
    kernels = _cell_integral_kernels(
        compiled_form,
        sum_duplicate_cell_integrals=sum_duplicate_cell_integrals,
    )
    unknown_tags = [] if -1 in kernels else sorted(set(map(int, tags)) - set(kernels))
    if unknown_tags:
        raise ValueError(f"compiled form has no cell integral for tags {unknown_tags}")

    element = function_space.element
    basix_element = element.basix_element
    dimension = int(element.space_dimension)
    exact_form_identity = (
        _mesh_actual_form_identity(compiled_form, element, kernels)
        if geometry_policy == "mesh_actual_exact"
        else None
    )
    if geometry_policy == "mesh_actual_exact" and raw_tensor_evaluator is not None:
        if (
            getattr(raw_tensor_evaluator, "identity", None)
            != "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1"
            or getattr(raw_tensor_evaluator, "profile_name", None)
            != "task41_p0_v6_b0_actual_qmetric"
        ):
            raise ValueError(
                "mesh_actual_exact accepts only the explicitly reviewed V6 actual-qmetric evaluator"
            )
        raw_tensor_evaluator.validate_compiled_form(compiled_form, kernels)
    entity_dofs = basix_element.entity_dofs
    interior_positions = np.asarray(entity_dofs[tdim][0], dtype=np.int32)
    if len(interior_positions) == 0:
        raise ValueError("selected H(curl) element has no cell-interior DoFs")
    trace_positions = np.setdiff1d(
        np.arange(dimension, dtype=np.int32),
        interior_positions,
        assume_unique=True,
    )

    compact_map_preflight: dict[str, Any] | None = None
    if compact_action_only_maps:
        if comm.size != 1:
            raise NotImplementedError("compact action-only volume maps require MPI1")
        full_rows_upper = int(dofmap.index_map.size_global)
        index_bytes = int(np.dtype(PETSc.IntType).itemsize)
        scalar_bytes = int(np.dtype(np.complex128).itemsize)
        slave_count = 0
        coefficient_count = 0
        if mpc is not None:
            slave_count = int(len(np.asarray(mpc.slaves).reshape(-1)))
            mpc_coefficients, _mpc_offsets = mpc.coefficients()
            coefficient_count = int(len(mpc_coefficients))
        _checked_petsc_index_scalar(full_rows_upper, "compact full_rows")
        row_maps_bytes = 3 * full_rows_upper * index_bytes
        per_cell_index_bytes = owned_cells * (2 * dimension + len(interior_positions)) * index_bytes
        slave_expansion_bytes = (
            coefficient_count * (index_bytes + scalar_bytes)
            + (slave_count + 1) * np.dtype(np.int64).itemsize
        )
        active_original_bytes = full_rows_upper * index_bytes
        python_cell_metadata_bytes = owned_cells * 512
        compact_map_preflight = {
            "schema": "task40extra.review_v25_compact_volume_maps_preflight.v1",
            "status": "DERIVED_UPPER_BOUND",
            "mpi_size": int(comm.size),
            "full_rows_upper": full_rows_upper,
            "owned_cells": owned_cells,
            "local_dofs_per_cell": dimension,
            "interior_rows_per_cell": len(interior_positions),
            "trace_rows_per_cell": len(trace_positions),
            "finalized_slave_rows": slave_count,
            "finalized_master_coefficients": coefficient_count,
            "dense_row_map_bytes": row_maps_bytes,
            "cell_index_and_recovery_map_bytes_upper": per_cell_index_bytes,
            "slave_expansion_csr_bytes_upper": slave_expansion_bytes,
            "active_original_rows_bytes_upper": active_original_bytes,
            "python_cell_metadata_bytes_upper": python_cell_metadata_bytes,
            "retained_numeric_bytes_upper": int(
                row_maps_bytes
                + per_cell_index_bytes
                + slave_expansion_bytes
                + active_original_bytes
                + python_cell_metadata_bytes
            ),
            "workspace_bytes": int(
                owned_cells * dimension * index_bytes
                + owned_cells * len(interior_positions) * index_bytes
                + 2 * full_rows_upper * index_bytes
            ),
            "scope": "compact MPI1 index maps, exact slave/master closure, local dofmaps and recovery-map owners; class caches and native callback vectors are gated separately",
        }
        if allocation_gate is not None:
            allocation_gate("compact_action_only_maps_preflight", compact_map_preflight)

    local_cell_dofs: list[np.ndarray] = []
    local_interiors: list[np.ndarray] = []
    for cell in range(owned_cells):
        local = np.asarray(dofmap.cell_dofs(cell), dtype=np.int32)
        original = _checked_petsc_index_array(
            dofmap.index_map.local_to_global(local), "cell global DoF rows"
        )
        local_cell_dofs.append(original)
        local_interiors.append(original[interior_positions])
    owned_trace, mapping, trace_rows, full_rows = _owned_trace_numbering(
        function_space,
        tuple(local_interiors),
        compact=compact_action_only_maps,
    )
    trace_constraints = _trace_constraint_map(
        function_space,
        owned_trace,
        mapping,
        trace_rows,
        mpc,
        compact=compact_action_only_maps,
    )
    del local_interiors
    if compact_map_preflight is not None:
        compact_map_preflight["measured_trace_rows"] = int(trace_rows)
        compact_map_preflight["measured_active_rows"] = int(trace_constraints.active_rows)
        compact_map_preflight["measured_slave_rows"] = int(trace_constraints.slave_rows)
        compact_map_preflight["trace_constraint_map_audit"] = dict(
            trace_constraints.build_audit
        )
    active_rows = trace_constraints.active_rows
    owned_active = trace_constraints.owned_active_original_dofs
    active_counts = tuple(comm.allgather(len(owned_active)))
    active_start = int(sum(active_counts[: comm.rank]))
    local_appended = appended_global_rows if comm.rank == comm.size - 1 else 0
    matrix_rows = active_rows + appended_global_rows
    cell_trace_data: list[tuple[np.ndarray, sparse.csr_matrix, bool]] = []
    if materialize_global_matrix:
        for original_dofs in local_cell_dofs:
            cell_trace_data.append(
                _cell_trace_expansion(
                    original_dofs[trace_positions],
                    trace_constraints,
                )
            )
    if materialize_global_matrix:
        preallocation_started = perf_counter()
        diagonal_nnz, off_diagonal_nnz, preallocation_audit = (
            _distributed_trace_preallocation(
                comm,
                tuple(data[0] for data in cell_trace_data),
                active_counts=active_counts,
                appended_global_rows=appended_global_rows,
                appended_support_owned_cell_groups=(appended_support_owned_cell_groups),
                appended_support_group_by_row=(appended_support_group_by_row),
                dense_appended_block=dense_appended_block,
            )
        )
        preallocation_audit["build_seconds"] = float(
            comm.allreduce(
                perf_counter() - preallocation_started,
                op=MPI.MAX,
            )
        )
        if allocation_gate is not None:
            allocation_gate(
                "condensed_matrix",
                {
                    "rows": int(matrix_rows),
                    "nnz": int(preallocation_audit["preallocated_structural_nnz"]),
                    "matrix_payload_bytes": int(
                        (matrix_rows + 1) * np.dtype(PETSc.IntType).itemsize
                        + int(preallocation_audit["preallocated_structural_nnz"])
                        * (
                            np.dtype(PETSc.IntType).itemsize
                            + np.dtype(PETSc.ScalarType).itemsize
                        )
                    ),
                    "workspace_bytes": 0,
                    "gate_scope": "before_PETSc_condensed_matrix_creation",
                },
            )
        condensed = PETSc.Mat().createAIJ(
            size=(
                (len(owned_active) + local_appended, matrix_rows),
                (len(owned_active) + local_appended, matrix_rows),
            ),
            nnz=(diagonal_nnz if comm.size == 1 else (diagonal_nnz, off_diagonal_nnz)),
            comm=comm,
        )
        if condensed.getOwnershipRange()[0] != active_start:
            condensed.destroy()
            raise RuntimeError(
                "PETSc active-trace ownership disagrees with trace numbering"
            )
        condensed.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)
    else:
        condensed = None
        preallocation_audit = {
            "status": "not_run_action_only",
            "build_seconds": None,
        }

    mesh.topology.create_entity_permutations()
    cell_permutations = mesh.topology.get_cell_permutation_info()
    local_class_coordinates: dict[tuple[Any, ...], np.ndarray] = {}
    cell_raw_metadata: list[tuple[tuple[Any, ...], tuple[Any, ...]]] = []
    exact_coordinate_bytes: dict[tuple[Any, ...], bytes] = {}
    exact_class_descriptors: dict[tuple[Any, ...], dict[str, Any]] = {}
    exact_cells_by_oriented_class: dict[tuple[Any, ...], list[int]] = {}
    exact_build_cell_order = list(range(owned_cells))
    exact_probe_count = 0
    exact_material_hashes: dict[int, str] = {}
    local_metadata_error = None
    try:
        for cell in range(owned_cells):
            tag = int(tags[cell])
            if geometry_policy == "mesh_actual_exact":
                actual_coordinates, widths = _mesh_actual_exact_coordinates(
                    mesh, cell, tolerance=geometry_tolerance
                )
                if tag not in exact_material_hashes:
                    exact_material_hashes[tag] = _mesh_actual_material_sha256(
                        exact_form_identity,
                        tag=tag,
                        material_identity=(geometry_material_identity_by_tag or {}).get(tag),
                        raw_tensor_evaluator_identity=(
                            None
                            if raw_tensor_evaluator is None
                            else _raw_tensor_evaluator_cache_identity(
                                raw_tensor_evaluator
                            )
                        ),
                    )
                raw_key, coordinate_bytes = _mesh_actual_raw_key(
                    compiled_form,
                    element,
                    kernels,
                    tag=tag,
                    coordinates=actual_coordinates,
                    material_identity=(geometry_material_identity_by_tag or {}).get(tag),
                    form_identity=exact_form_identity,
                    material_sha256=exact_material_hashes[tag],
                    raw_tensor_evaluator_identity=(
                        None
                        if raw_tensor_evaluator is None
                        else _raw_tensor_evaluator_cache_identity(
                            raw_tensor_evaluator
                        )
                    ),
                )
                previous_bytes = exact_coordinate_bytes.get(raw_key)
                if previous_bytes is not None and previous_bytes != coordinate_bytes:
                    raise RuntimeError(
                        "mesh_actual_exact coordinate digest collision detected"
                    )
                exact_coordinate_bytes[raw_key] = coordinate_bytes
                coordinates_for_kernel = actual_coordinates
                policy_raw_key = raw_key
                oriented_key = (raw_key, int(cell_permutations[cell]))
                exact_class_descriptors.setdefault(
                    oriented_key,
                    {
                        "cell_index": int(cell),
                        "tag": int(tag),
                        "widths": [float(value) for value in widths],
                        "center": np.asarray(actual_coordinates).mean(axis=0).tolist(),
                        "permutation": int(cell_permutations[cell]),
                    },
                )
                exact_cells_by_oriented_class.setdefault(oriented_key, []).append(int(cell))
            else:
                canonical_coordinates, widths = _canonical_axis_aligned_coordinates(
                    mesh,
                    cell,
                    tolerance=geometry_tolerance,
                    preserve_exact_geometry=preserve_exact_geometry,
                )
                raw_key = (tag, *widths)
                policy_raw_key = ("actual_space", *raw_key)
                coordinates_for_kernel = canonical_coordinates
            previous = local_class_coordinates.get(policy_raw_key)
            if previous is not None and not np.array_equal(
                previous,
                coordinates_for_kernel,
            ):
                raise RuntimeError(
                    "raw tensor class has inconsistent geometry "
                    "on one MPI rank"
                )
            local_class_coordinates.setdefault(
                policy_raw_key,
                coordinates_for_kernel,
            )
            cell_raw_metadata.append((raw_key, policy_raw_key))
    except Exception as error:
        local_metadata_error = f"{type(error).__name__}: {error}"
    metadata_errors = comm.allgather(local_metadata_error)
    if any(error is not None for error in metadata_errors):
        if condensed is not None:
            condensed.destroy()
        error_class = (
            ValueError
            if all(
                error is None or error.startswith("ValueError:")
                for error in metadata_errors
            )
            else TypeError
            if all(
                error is None or error.startswith("TypeError:")
                for error in metadata_errors
            )
            else RuntimeError
        )
        raise error_class(
            "raw tensor class metadata failed before global dedup: "
            + "; ".join(
                f"rank {rank}: {error}"
                for rank, error in enumerate(metadata_errors)
                if error is not None
            )
        )
    if allocation_gate is not None and geometry_policy == "canonical":
        # This gate is deliberately based only on the class metadata already
        # collected above.  It runs before the raw tensor broadcast and the
        # first oriented Schur class are materialized, so the caller can
        # reserve the shared temporary window without probing platform RSS or
        # evaluating a full cell tensor just to estimate its size.
        local_raw_classes = {
            policy_raw_key for _raw_key, policy_raw_key in cell_raw_metadata
        }
        local_oriented_classes = {
            (raw_key, int(cell_permutations[cell]))
            for cell, (raw_key, _policy_raw_key) in enumerate(cell_raw_metadata)
        }
        raw_class_packets = comm.allgather(tuple(local_raw_classes))
        oriented_class_packets = comm.allgather(tuple(local_oriented_classes))
        global_raw_classes = {
            key for packet in raw_class_packets for key in packet
        }
        global_oriented_classes = {
            key for packet in oriented_class_packets for key in packet
        }
        scalar_bytes = int(np.dtype(np.complex128).itemsize)
        real_bytes = int(np.dtype(np.float64).itemsize)
        index_bytes = int(np.dtype(PETSc.IntType).itemsize)
        interior_dimension = int(len(interior_positions))
        trace_dimension = int(len(trace_positions))
        identity_class_count = (
            1 if share_identity_cache and global_oriented_classes else len(global_oriented_classes)
        )
        condensation_capacity = assembly_time_condensation_capacity_facts(
            dimension=int(dimension),
            interior_dimension=interior_dimension,
            trace_dimension=trace_dimension,
            raw_class_count=len(global_raw_classes),
            oriented_class_count=len(global_oriented_classes),
            identity_class_count=identity_class_count,
            retain_local_schur=retain_local_schur_for_matrix_free,
            scalar_bytes=scalar_bytes,
            index_bytes=index_bytes,
            real_bytes=real_bytes,
        )
        # One oriented tensor is transformed at a time.  The block extracts
        # are copies, while the retained LU/recovery arrays are accounted for
        # separately above.  The two Schur terms cover the sparse constrained
        # product's output and one transient product buffer.
        retained_numeric_bytes_upper = int(
            condensation_capacity["retained_numeric_bytes_upper"]
        )
        raw_cache_bytes_upper = int(condensation_capacity["raw_cache_bytes_upper"])
        oriented_tensor_bytes_upper = int(
            condensation_capacity["oriented_tensor_bytes_upper"]
        )
        schur_cache_bytes_upper = int(
            condensation_capacity["schur_cache_bytes_upper"]
        )
        local_working_bytes_upper = int(
            condensation_capacity["local_working_bytes_upper"]
        )
        raw_tensor_candidate_workspace_bytes_upper = int(
            0
            if raw_tensor_evaluator is None
            else raw_tensor_evaluator.workspace_bytes_upper
        )
        allocation_gate(
            "cell_tensor_working_set",
            {
                "retained_numeric_bytes_upper": retained_numeric_bytes_upper,
                "workspace_bytes": int(
                    raw_cache_bytes_upper
                    + oriented_tensor_bytes_upper
                    + schur_cache_bytes_upper
                    + local_working_bytes_upper
                    + raw_tensor_candidate_workspace_bytes_upper
                ),
                "raw_cache_bytes_upper": raw_cache_bytes_upper,
                "oriented_tensor_bytes_upper": oriented_tensor_bytes_upper,
                "schur_cache_bytes_upper": schur_cache_bytes_upper,
                "local_working_bytes_upper": local_working_bytes_upper,
                "raw_tensor_candidate_workspace_bytes_upper": (
                    raw_tensor_candidate_workspace_bytes_upper
                ),
                "raw_class_count_local": int(len(local_raw_classes)),
                "raw_class_count_global_unique": int(len(global_raw_classes)),
                "oriented_class_count_local": int(len(local_oriented_classes)),
                "oriented_class_count_global_unique": int(
                    len(global_oriented_classes)
                ),
                "tensor_dimension": int(dimension),
                "interior_dimension": interior_dimension,
                "trace_dimension": trace_dimension,
                "gate_scope": "before_raw_and_oriented_cell_tensor_cache_construction",
            },
        )
    elif allocation_gate is not None:
        exact_raw_classes = {raw_key for raw_key, _policy_raw_key in cell_raw_metadata}
        exact_oriented_classes = {
            (raw_key, int(cell_permutations[cell]))
            for cell, (raw_key, _policy_raw_key) in enumerate(cell_raw_metadata)
        }
        exact_count = len(exact_oriented_classes)
        descriptors = exact_class_descriptors
        class_order = list(descriptors)
        selected_keys: list[tuple[Any, ...]] = []
        covered_strata: set[tuple[int, int]] = set()
        selected_sample_cell: dict[tuple[Any, ...], int] = {}
        if any(cell < 0 or cell >= owned_cells for cell in required_prefix_cells):
            raise IndexError("required exact-prefix cell lies outside owned cells")
        for cell in required_prefix_cells:
            raw_key = cell_raw_metadata[cell][0]
            key = (raw_key, int(cell_permutations[cell]))
            if key not in selected_sample_cell:
                selected_keys.append(key)
                selected_sample_cell[key] = cell
            covered_strata.add(
                (int(descriptors[key]["tag"]), int(descriptors[key]["permutation"]))
            )
        if len(selected_keys) > min(8, exact_count):
            raise ValueError("required exact-prefix cells exceed the eight-key V5 prefix cap")
        for key in class_order:
            descriptor = descriptors[key]
            stratum = (int(descriptor["tag"]), int(descriptor["permutation"]))
            if (
                stratum not in covered_strata
                and key not in selected_sample_cell
                and len(selected_keys) < min(8, exact_count)
            ):
                selected_keys.append(key)
                selected_sample_cell[key] = int(descriptor["cell_index"])
                covered_strata.add(stratum)
        feature_rows = [
            np.asarray([*descriptors[key]["center"], *descriptors[key]["widths"]], dtype=np.float64)
            for key in class_order
        ]
        if feature_rows:
            features = np.stack(feature_rows)
            spans = np.ptp(features, axis=0)
            spans[spans == 0.0] = 1.0
            normalized = (features - features.min(axis=0)) / spans
            while len(selected_keys) < min(8, exact_count):
                selected_positions = [class_order.index(key) for key in selected_keys]
                remaining_positions = [
                    index for index, key in enumerate(class_order) if key not in selected_keys
                ]
                if not selected_positions:
                    chosen_position = remaining_positions[0]
                else:
                    chosen_position = max(
                        remaining_positions,
                        key=lambda index: (
                            min(float(np.linalg.norm(normalized[index] - normalized[chosen])) for chosen in selected_positions),
                            -int(descriptors[class_order[index]]["cell_index"]),
                        ),
                    )
                chosen_key = class_order[chosen_position]
                selected_keys.append(chosen_key)
                selected_sample_cell[chosen_key] = int(descriptors[chosen_key]["cell_index"])
        sample_cells = [selected_sample_cell[key] for key in selected_keys]
        required_qualification_cells = tuple(
            int(value)
            for value in getattr(
                raw_tensor_evaluator,
                "required_prefix_sample_cell_indices",
                (),
            )
        )
        if required_qualification_cells and (
            tuple(required_prefix_cells) != required_qualification_cells
            or tuple(sample_cells) != required_qualification_cells
            or len(set(selected_keys)) != len(required_qualification_cells)
        ):
            raise RuntimeError(
                "V6 actual-qmetric prefix does not match the frozen eight-key inventory"
            )
        sampled_cell_set = set(sample_cells)
        exact_build_cell_order = sample_cells + [
            cell for cell in range(owned_cells) if cell not in sampled_cell_set
        ]
        exact_probe_count = len(sample_cells)
        capacity = assembly_time_condensation_capacity_facts(
            dimension=int(dimension),
            interior_dimension=len(interior_positions),
            trace_dimension=len(trace_positions),
            raw_class_count=0,
            oriented_class_count=exact_count,
            identity_class_count=(1 if share_identity_cache and exact_count else exact_count),
            retain_local_schur=retain_local_schur_for_matrix_free,
            scalar_bytes=int(np.dtype(np.complex128).itemsize),
            index_bytes=int(np.dtype(PETSc.IntType).itemsize),
            real_bytes=int(np.dtype(np.float64).itemsize),
        )
        exact_capacity = capacity
        exact_class_count = exact_count
        prefix_count = exact_probe_count
        prefix_payload = (
            prefix_count * int(capacity["retained_per_oriented_class_bytes"])
            + int(capacity["identity_cache_bytes_upper"])
        )
        one_class_workspace = int(capacity["local_working_bytes_upper"])
        evaluator_prepare_workspace = int(
            0
            if raw_tensor_evaluator is None
            else getattr(
                raw_tensor_evaluator,
                "prepare_workspace_bytes_upper",
                raw_tensor_evaluator.workspace_bytes_upper,
            )
        )
        evaluator_key_workspace = int(
            0
            if raw_tensor_evaluator is None
            else getattr(
                raw_tensor_evaluator,
                "key_workspace_bytes_upper",
                raw_tensor_evaluator.workspace_bytes_upper,
            )
        )
        evaluator_class_timing_bytes = int(
            0
            if raw_tensor_evaluator is None
            else getattr(
                raw_tensor_evaluator,
                "class_timing_metadata_bytes_upper",
                0,
            )
        )
        evaluator_scratch_bytes = int(
            0
            if raw_tensor_evaluator is None
            else getattr(raw_tensor_evaluator, "helper_scratch_bytes_upper", 0)
            + getattr(
                raw_tensor_evaluator,
                "original_kernel_oracle_scratch_bytes_upper",
                0,
            )
        )
        evaluator_shared_table_bytes = 0
        allocation_gate(
            "mesh_actual_exact_prefix_preflight",
            {
                "additional_payload_bytes": int(prefix_payload),
                "workspace_bytes": one_class_workspace + evaluator_prepare_workspace,
                "tensor_dimension": int(dimension),
                "interior_dimension": int(len(interior_positions)),
                "trace_dimension": int(len(trace_positions)),
                **(
                    {
                        "raw_tensor_candidate_prepare_workspace_bytes_upper": (
                            evaluator_prepare_workspace
                        ),
                        "raw_tensor_candidate_key_workspace_bytes_upper": (
                            evaluator_key_workspace
                        ),
                        "raw_tensor_candidate_class_timing_metadata_bytes_upper": (
                            evaluator_class_timing_bytes
                        ),
                        "raw_tensor_candidate_workspace_bytes_upper": (
                            evaluator_prepare_workspace
                        ),
                        "raw_tensor_candidate_helper_scratch_bytes_upper": int(
                            getattr(raw_tensor_evaluator, "helper_scratch_bytes_upper", 0)
                        ),
                        "raw_tensor_candidate_original_kernel_oracle_scratch_bytes_upper": int(
                            getattr(
                                raw_tensor_evaluator,
                                "original_kernel_oracle_scratch_bytes_upper",
                                0,
                            )
                        ),
                        "raw_tensor_candidate_scratch_bytes_upper": evaluator_scratch_bytes,
                    }
                    if raw_tensor_evaluator is not None
                    else {}
                ),
                "raw_key_count": len(exact_raw_classes),
                "oriented_key_count": exact_count,
                "prefix_misses_to_measure": prefix_count,
                "prefix_sample_cells": sample_cells,
                "prefix_sample_tag_orientation_strata": [
                    [int(descriptors[key]["tag"]), int(descriptors[key]["permutation"])]
                    for key in selected_keys
                ],
                "uncovered_tag_orientation_strata": [
                    [int(descriptors[key]["tag"]), int(descriptors[key]["permutation"])]
                    for key in class_order
                    if (int(descriptors[key]["tag"]), int(descriptors[key]["permutation"]))
                    not in covered_strata
                ],
                "retained_per_oriented_class_bytes": int(
                    capacity["retained_per_oriented_class_bytes"]
                ),
                "projected_retained_numeric_bytes_upper": int(
                    capacity["retained_numeric_bytes_upper"]
                ),
                "raw_cache_bytes_upper": 0,
                "raw_tensor_retention_policy": "one_exact_key_then_release_after_elimination",
                "key_inventory_status": "METADATA_ONLY",
                "exact_form_identity": list(exact_form_identity),
                "geometry_material_identity_by_tag": dict(
                    geometry_material_identity_by_tag or {}
                ),
                "exact_key_inventory": [
                    {
                        "raw_class_key": list(key[0]),
                        "permutation": int(key[1]),
                        **dict(descriptors[key]),
                    }
                    for key in class_order
                ],
                "gate_scope": (
                    "before_first_actual_kernel_or_qmetric_helper_preparation"
                    if raw_tensor_evaluator is not None
                    else "before_first_actual_rank2_kernel_tabulation"
                ),
                **(
                    {
                        "raw_tensor_evaluator_implementation": str(
                            raw_tensor_evaluator.identity
                        ),
                        "raw_tensor_evaluator_identity": _raw_tensor_evaluator_cache_identity(
                            raw_tensor_evaluator
                        ),
                    }
                    if raw_tensor_evaluator is not None
                    else {}
                ),
            },
        )
        evaluator_prepare_seconds = 0.0
        if raw_tensor_evaluator is not None:
            prepare_started = perf_counter()
            raw_tensor_evaluator.prepare()
            evaluator_prepare_seconds = float(perf_counter() - prepare_started)
            if hasattr(raw_tensor_evaluator, "preparation_seconds"):
                raw_tensor_evaluator.preparation_seconds = evaluator_prepare_seconds
            evaluator_shared_table_bytes = int(
                getattr(raw_tensor_evaluator, "shared_table_bytes_upper", 0)
            )
    else:
        evaluator_workspace = 0
        evaluator_prepare_seconds = 0.0
    if geometry_policy == "mesh_actual_exact":
        raw_cache = {}
        local_kernel_seconds = 0.0
        raw_cache_audit = {
            "raw_tensor_class_count_sum": 0,
            "raw_tensor_class_use_count_sum": len(cell_raw_metadata),
            "raw_tensor_class_count_global_unique": len(local_class_coordinates),
            "raw_tensor_global_owner_policy": "mesh_actual_exact_local_key_stream",
            "raw_tensor_cross_rank_dedup_active": False,
            "raw_tensor_retention_policy": (
                "one_actual_qmetric_blocked_tensor_per_new_oriented_key_then_release"
                if raw_tensor_evaluator is not None
                else "one_actual_rank2_tensor_per_new_oriented_key_then_release"
            ),
            **(
                {
                    "raw_tensor_evaluator_implementation": str(
                        raw_tensor_evaluator.identity
                    ),
                    "raw_tensor_evaluator_identity": _raw_tensor_evaluator_cache_identity(
                        raw_tensor_evaluator
                    ),
                    "raw_tensor_evaluator_prepare_seconds": float(
                        evaluator_prepare_seconds
                    ),
                }
                if raw_tensor_evaluator is not None
                else {}
            ),
        }
    else:
        policy_forms: dict[str, tuple[Any, dict[int, Any], int]] = {
            "actual_space": (compiled_form, kernels, dimension),
        }
        try:
            raw_cache, raw_cache_audit, local_kernel_seconds = _global_raw_tensor_cache(
                comm,
                local_class_coordinates,
                policy_forms,
                raw_tensor_evaluator=raw_tensor_evaluator,
            )
        except Exception:
            if condensed is not None:
                condensed.destroy()
            raise
    schur_cache: dict[tuple[Any, ...], np.ndarray] = {}
    recovery_cache: dict[tuple[Any, ...], np.ndarray] = {}
    lu_cache: dict[tuple[Any, ...], tuple[np.ndarray, np.ndarray]] = {}
    rhs_projection_cache: dict[tuple[Any, ...], np.ndarray] = {}
    solution_embedding_cache: dict[tuple[Any, ...], np.ndarray] = {}
    rhs_trace_cache: dict[tuple[Any, ...], np.ndarray] = {}
    residual_projection_cache: dict[tuple[Any, ...], np.ndarray] = {}
    recovery_maps: list[CellRecoveryMap | None] = (
        [None] * owned_cells
        if geometry_policy == "mesh_actual_exact"
        else []
    )
    exact_probe_records: list[dict[str, Any]] = []
    exact_cache_misses = 0
    exact_full_admission_passed = False
    action_tensor_identities: dict[str, Any] = {}
    local_schur_seconds = 0.0
    local_orientation_seconds = 0.0
    local_tensor_hash_seconds = 0.0
    local_tensor_prepare_seconds = 0.0
    local_lu_solve_seconds = 0.0
    local_schur_product_seconds = 0.0
    local_observer_seconds = 0.0
    local_release_seconds = 0.0
    local_insert_seconds = 0.0
    local_lu_residual_max = 0.0
    shared_interior_identity = None
    if share_identity_cache:
        shared_interior_identity = np.eye(
            len(interior_positions), dtype=np.float64
        )
        shared_interior_identity.setflags(write=False)
    cell_build_order = (
        exact_build_cell_order
        if geometry_policy == "mesh_actual_exact"
        else list(range(owned_cells))
    )
    for cell in cell_build_order:
        original_dofs = local_cell_dofs[cell]
        metadata = cell_raw_metadata[cell]
        raw_key, policy_raw_key = metadata
        class_key = (
            *raw_key,
            int(cell_permutations[cell]),
        )
        exact_oriented_key = (raw_key, int(cell_permutations[cell]))
        schur = schur_cache.get(class_key)
        if schur is None:
            kernel_seconds = 0.0
            prefix_validation = None
            observer_seconds = 0.0
            tensor_prepare_seconds = 0.0
            if geometry_policy == "mesh_actual_exact":
                raw_started = perf_counter()
                if raw_tensor_evaluator is None:
                    tensor = _tabulate_raw_tensor_class(
                        compiled_form,
                        kernels,
                        local_class_coordinates[policy_raw_key],
                        tag=int(tags[cell]),
                        dimension=dimension,
                    )
                else:
                    tensor = raw_tensor_evaluator(
                        compiled_form,
                        kernels,
                        local_class_coordinates[policy_raw_key],
                        tag=int(tags[cell]),
                        dimension=dimension,
                    )
                kernel_seconds = perf_counter() - raw_started
                local_kernel_seconds += kernel_seconds
            else:
                tensor = raw_cache[policy_raw_key]
            orientation_started = perf_counter()
            oriented = tensor.copy()
            _orient_cell_tensor(
                element,
                oriented,
                np.asarray(
                    cell_permutations[cell : cell + 1],
                    dtype=np.uint32,
                ),
            )
            orientation_seconds = perf_counter() - orientation_started
            local_orientation_seconds += orientation_seconds
            schur_started = perf_counter()
            if not materialize_global_matrix:
                # Bind the complete physical tensor before elimination.  Only
                # digests survive; no extra full local tensor is retained.
                hash_started = perf_counter()
                action_tensor_identities[repr(class_key)] = {
                    "shape": list(oriented.shape), "dtype": str(oriented.dtype),
                    "raw_sha256": hashlib.sha256(memoryview(np.ascontiguousarray(tensor)).cast("B")).hexdigest(),
                    "oriented_sha256": hashlib.sha256(memoryview(np.ascontiguousarray(oriented)).cast("B")).hexdigest(),
                }
                tensor_hash_seconds = perf_counter() - hash_started
            else:
                tensor_hash_seconds = 0.0
            tensor_prepare_started = perf_counter()
            A_ii = oriented[np.ix_(interior_positions, interior_positions)]
            A_it = oriented[np.ix_(interior_positions, trace_positions)]
            A_ti = oriented[np.ix_(trace_positions, interior_positions)]
            A_tt = oriented[np.ix_(trace_positions, trace_positions)]
            blocks = {"K": A_ii, "G": A_it, "J": A_ti, "L": A_tt}
            if geometry_policy == "mesh_actual_exact":
                tensor_prepare_seconds = perf_counter() - tensor_prepare_started
                local_tensor_hash_seconds += tensor_hash_seconds
                local_tensor_prepare_seconds += tensor_prepare_seconds
            lu_started = perf_counter()
            try:
                if strict_local_checks:
                    interior_lu, lu_residual = _strict_local_lu(A_ii)
                    local_lu_residual_max = max(
                        local_lu_residual_max, float(lu_residual)
                    )
                else:
                    interior_lu = lu_factor(A_ii)
            except Exception:
                # The matrix exists before local classes are factored.  Do
                # not leave an abnormal setup with a live PETSc allocation.
                if condensed is not None:
                    condensed.destroy()
                raise
            interior_from_trace = -lu_solve(
                interior_lu,
                A_it,
            )
            adjoint_trace_solution = lu_solve(
                interior_lu,
                A_ti.conj().T,
                trans=2,
            )
            trace_from_interior_rhs = -adjoint_trace_solution.conj().T
            lu_seconds = perf_counter() - lu_started
            local_lu_solve_seconds += lu_seconds
            schur_product_started = perf_counter()
            schur = A_tt + A_ti @ interior_from_trace
            schur_product_seconds = perf_counter() - schur_product_started
            local_schur_product_seconds += schur_product_seconds
            local_schur_seconds += perf_counter() - schur_started
            if geometry_policy == "mesh_actual_exact" and prefix_cell_validator is not None:
                raw_key_for_cell, _ = metadata
                for prefix_cell in exact_cells_by_oriented_class[exact_oriented_key]:
                    if prefix_cell not in required_prefix_cells:
                        continue
                    prefix_original_dofs = local_cell_dofs[prefix_cell]
                    prefix_active_ids, prefix_trace_expansion, _ = _cell_trace_expansion(
                        prefix_original_dofs[trace_positions],
                        trace_constraints,
                    )
                    validation = dict(
                        prefix_cell_validator(
                            int(prefix_cell),
                            local_class_coordinates[raw_key_for_cell],
                            blocks,
                            {
                                "raw_tensor": tensor,
                                "oriented_tensor": oriented,
                                "raw_tensor_evaluator": raw_tensor_evaluator,
                                "cell_index": int(prefix_cell),
                                "tag": int(tags[prefix_cell]),
                                "element": element,
                                "permutation": int(cell_permutations[prefix_cell]),
                                "interior_positions": interior_positions,
                                "trace_positions": trace_positions,
                                "original_dofs": prefix_original_dofs,
                                "R": interior_from_trace,
                                "T": trace_from_interior_rhs,
                                "S": schur,
                                "strict_lu_residual": float(
                                    lu_residual if strict_local_checks else 0.0
                                ),
                                "candidate_build_seconds": float(kernel_seconds),
                                "trace_expansion": prefix_trace_expansion,
                                "active_ids": prefix_active_ids,
                            },
                        )
                    )
                    if prefix_cell == int(cell):
                        prefix_validation = validation
            schur_cache[class_key] = schur
            recovery_cache[class_key] = interior_from_trace
            lu_cache[class_key] = interior_lu
            if shared_interior_identity is None:
                interior_identity = np.eye(
                    len(interior_positions),
                    dtype=np.float64,
                )
            else:
                interior_identity = shared_interior_identity
            rhs_projection_cache[class_key] = interior_identity
            solution_embedding_cache[class_key] = interior_identity
            rhs_trace_cache[class_key] = trace_from_interior_rhs
            residual_projection_cache[class_key] = interior_identity
            if exact_cell_observer is not None:
                observer_started = perf_counter()
                raw_key_for_cell, _ = metadata
                for observed_cell in exact_cells_by_oriented_class[exact_oriented_key]:
                    active_ids, trace_expansion, _identity = _cell_trace_expansion(
                        local_cell_dofs[observed_cell][trace_positions],
                        trace_constraints,
                    )
                    exact_cell_observer(
                        int(observed_cell),
                        local_class_coordinates[raw_key_for_cell],
                        blocks,
                        {
                            "class_key": class_key,
                            "original_dofs": local_cell_dofs[observed_cell],
                            "interior_positions": interior_positions,
                            "trace_positions": trace_positions,
                            "trace_expansion": trace_expansion,
                            "active_ids": active_ids,
                            "R": interior_from_trace,
                            "T": trace_from_interior_rhs,
                            "S": schur,
                        },
                    )
                observer_seconds = perf_counter() - observer_started
                local_observer_seconds += observer_seconds
            if geometry_policy == "mesh_actual_exact":
                exact_cache_misses += 1
                release_started = perf_counter()
                del tensor, oriented, blocks, A_ii, A_it, A_ti, A_tt, adjoint_trace_solution
                release_seconds = perf_counter() - release_started
                local_release_seconds += release_seconds
                if len(exact_probe_records) < exact_probe_count:
                    exact_probe_records.append(
                        {
                            "cell_index": int(cell),
                            "raw_key": repr(raw_key),
                            "oriented_key": repr(class_key),
                            "cell_tag": int(tags[cell]),
                            "permutation": int(cell_permutations[cell]),
                            "kernel_seconds": float(kernel_seconds),
                            "orientation_seconds": float(orientation_seconds),
                            "tensor_hash_seconds": float(tensor_hash_seconds),
                            "tensor_prepare_seconds": float(tensor_prepare_seconds),
                            "lu_solve_seconds": float(lu_seconds),
                            "schur_seconds": float(schur_product_seconds),
                            "observer_seconds": float(observer_seconds),
                            "release_seconds": float(release_seconds),
                            "reference_validation": prefix_validation,
                        }
                    )
                    if len(exact_probe_records) == exact_probe_count:
                        phase_names = (
                            "kernel_seconds",
                            "orientation_seconds",
                            "tensor_hash_seconds",
                            "tensor_prepare_seconds",
                            "lu_solve_seconds",
                            "schur_seconds",
                            "observer_seconds",
                            "release_seconds",
                        )
                        phase_max = {
                            name: max(float(row[name]) for row in exact_probe_records)
                            for name in phase_names
                        }
                        phase_mean = {
                            name: float(np.mean([row[name] for row in exact_probe_records]))
                            for name in phase_names
                        }
                        remaining_misses = max(0, int(exact_class_count) - exact_probe_count)
                        conservative_per_class = float(sum(phase_max.values()))
                        projected_build_seconds = remaining_misses * conservative_per_class
                        projected_retained = int(
                            exact_capacity["retained_numeric_bytes_upper"]
                        )
                        prefix_retained = (
                            exact_probe_count
                            * int(exact_capacity["retained_per_oriented_class_bytes"])
                            + int(exact_capacity["identity_cache_bytes_upper"])
                        )
                        exact_metadata_bytes_upper = (
                            len(exact_coordinate_bytes) * (8 * 3 * 8 + 8 * 3 * 8 + 1024)
                            + owned_cells * 512
                        )
                        prefix_qualification = None
                        if raw_tensor_evaluator is not None and getattr(
                            raw_tensor_evaluator,
                            "requires_prefix_qualification",
                            False,
                        ):
                            prefix_qualification = (
                                raw_tensor_evaluator.prefix_qualification_audit()
                            )
                            if (
                                prefix_qualification.get("full_admission_eligible")
                                is not True
                                or prefix_qualification.get("status")
                                != "PREFIX_QUALIFIED"
                                or [row.get("cell_index") for row in exact_probe_records]
                                != list(required_qualification_cells)
                                or any(
                                    not isinstance(row.get("reference_validation"), Mapping)
                                    or row["reference_validation"].get("status") != "PASS"
                                    for row in exact_probe_records
                                )
                            ):
                                raise RuntimeError(
                                    "V6 eight-key original-kernel prefix qualification is incomplete or failed"
                                )
                        allocation_gate(
                            "mesh_actual_exact_full_admission",
                            {
                                "additional_payload_bytes": max(
                                    0, projected_retained - prefix_retained
                                ),
                                "workspace_bytes": int(
                                    exact_capacity["local_working_bytes_upper"]
                                    + evaluator_key_workspace
                                    + evaluator_class_timing_bytes
                                    + evaluator_shared_table_bytes
                                ),
                                **(
                                    {
                                        "raw_tensor_candidate_prepare_workspace_bytes_upper": (
                                            evaluator_prepare_workspace
                                        ),
                                        "raw_tensor_candidate_workspace_bytes_upper": (
                                            evaluator_key_workspace
                                        ),
                                        "raw_tensor_candidate_key_workspace_bytes_upper": (
                                            evaluator_key_workspace
                                        ),
                                        "raw_tensor_candidate_class_timing_metadata_bytes_upper": (
                                            evaluator_class_timing_bytes
                                        ),
                                        "raw_tensor_candidate_shared_table_bytes": int(
                                            evaluator_shared_table_bytes
                                        ),
                                        "raw_tensor_evaluator_identity": _raw_tensor_evaluator_cache_identity(
                                            raw_tensor_evaluator
                                        ),
                                    }
                                    if raw_tensor_evaluator is not None
                                    else {}
                                ),
                                "raw_key_count": len(exact_coordinate_bytes),
                                "oriented_key_count": int(exact_class_count),
                                "measured_prefix_cache_misses": len(exact_probe_records),
                                "prefix_records": exact_probe_records,
                                **(
                                    {"prefix_qualification": prefix_qualification}
                                    if prefix_qualification is not None
                                    else {}
                                ),
                                "prefix_phase_mean_seconds": phase_mean,
                                "prefix_phase_max_seconds": phase_max,
                                "prefix_phase_timing_scope": {
                                    "tensor_hash_seconds": (
                                        "SHA-256 over the complete raw and oriented local tensors"
                                    ),
                                    "tensor_prepare_seconds": (
                                        "K/G/J/L block extraction and any frozen prefix-cell validation; excludes tensor_hash_seconds"
                                    ),
                                    "schur_seconds": "Schur product only",
                                },
                                "projected_remaining_class_build_seconds_upper": projected_build_seconds,
                                "remaining_miss_projection_method": "sum per-phase maxima from a tag/orientation/coordinate-spread sample",
                                "post_build_action_checker_seconds_reserve": "must_be_added_by_fixed_window_controller_before_admission",
                                "projected_retained_numeric_bytes_upper": projected_retained,
                                "prefix_retained_numeric_bytes_already_resident": int(prefix_retained),
                                "exact_key_and_cell_metadata_bytes_upper": int(exact_metadata_bytes_upper),
                                "projected_condensation_and_key_bytes_upper": int(
                                    projected_retained + exact_metadata_bytes_upper
                                ),
                                "raw_cache_bytes_upper": 0,
                                "raw_tensor_retention_policy": "one_exact_key_then_release_after_elimination",
                                "time_gate_status": "requires_build_plus_two_column_action_write_and_independent_checker_balance",
                            },
                        )
                        exact_full_admission_passed = True
        trace_original = original_dofs[trace_positions]
        if materialize_global_matrix:
            active_ids, local_expansion, identity_expansion = cell_trace_data[cell]
            active_schur = _constrain_local_schur(
                schur,
                local_expansion,
                identity_expansion,
            )
            insert_started = perf_counter()
            assert condensed is not None
            condensed.setValues(
                active_ids,
                active_ids,
                np.asarray(active_schur, dtype=PETSc.ScalarType),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
            local_insert_seconds += perf_counter() - insert_started
        cell_map = CellRecoveryMap(
            interior_original_dofs=original_dofs[interior_positions],
            trace_original_dofs=trace_original,
            class_key=class_key,
        )
        if geometry_policy == "mesh_actual_exact":
            recovery_maps[cell] = cell_map
        else:
            recovery_maps.append(cell_map)
    if materialize_global_matrix:
        preassembly_sync_started = perf_counter()
        comm.Barrier()
        preassembly_sync_seconds = float(
            comm.allreduce(
                perf_counter() - preassembly_sync_started,
                op=MPI.MAX,
            )
        )
        if defer_final_assembly:
            final_assembly_seconds = 0.0
        else:
            assembly_started = perf_counter()
            assert condensed is not None
            condensed.assemble()
            final_assembly_seconds = float(
                comm.allreduce(
                    perf_counter() - assembly_started,
                    op=MPI.MAX,
                )
            )
    else:
        preassembly_sync_seconds = None
        final_assembly_seconds = None
    if geometry_policy == "mesh_actual_exact":
        if not exact_full_admission_passed:
            raise RuntimeError("mesh_actual_exact full admission did not run")
        if any(cell_map is None for cell_map in recovery_maps):
            raise RuntimeError("mesh_actual_exact did not restore the original cell-map order")
        recovery_maps = [cell_map for cell_map in recovery_maps if cell_map is not None]
        raw_cache_audit["raw_tensor_class_count_sum"] = int(exact_cache_misses)
        raw_cache_audit["raw_tensor_class_count_global_unique"] = int(exact_cache_misses)
        if raw_tensor_evaluator is not None:
            raw_cache_audit["raw_tensor_evaluator"] = raw_tensor_evaluator.audit()
    interior_rows = full_rows - trace_rows
    global_cells = int(comm.allreduce(owned_cells, op=MPI.SUM))
    active_interior_rows = interior_rows
    raw_class_count = int(raw_cache_audit["raw_tensor_class_count_sum"])
    oriented_class_count = int(comm.allreduce(len(schur_cache), op=MPI.SUM))
    if retain_local_schur_for_matrix_free:
        for schur in schur_cache.values():
            schur.setflags(write=False)
        retained_class_count_local = len(schur_cache)
        retained_bytes_local = sum(int(schur.nbytes) for schur in schur_cache.values())
        retained_class_count_sum = int(
            comm.allreduce(retained_class_count_local, op=MPI.SUM)
        )
        retained_bytes_sum = int(comm.allreduce(retained_bytes_local, op=MPI.SUM))
    else:
        retained_class_count_local = 0
        retained_bytes_local = 0
        retained_class_count_sum = 0
        retained_bytes_sum = 0

    def unique_mapping_bytes(
        mappings: tuple[tuple[str, Mapping[Any, Any]], ...],
    ) -> dict[str, int]:
        """Count the fixed setup caches once even when aliases share arrays."""

        seen: set[int] = set()
        result: dict[str, int] = {}
        for name, mapping in mappings:
            amount = 0
            for value in mapping.values():
                values = value if isinstance(value, (tuple, list)) else (value,)
                for array in values:
                    if not isinstance(array, np.ndarray) or id(array) in seen:
                        continue
                    seen.add(id(array))
                    amount += int(array.nbytes)
            result[name] = amount
        result["retained_numeric_cache_bytes"] = int(sum(result.values()))
        return result

    retained_cache_bytes_local = unique_mapping_bytes(
        (
            ("lu_bytes", lu_cache),
            ("recovery_bytes", recovery_cache),
            ("rhs_trace_bytes", rhs_trace_cache),
            ("rhs_projection_bytes", rhs_projection_cache),
            ("solution_embedding_bytes", solution_embedding_cache),
            ("residual_projection_bytes", residual_projection_cache),
            (
                "retained_schur_bytes",
                schur_cache if retain_local_schur_for_matrix_free else {},
            ),
        )
    )
    assembly_temporary_bytes_local = {
        "raw_tensor_bytes": int(
            sum(_retained_array_bytes(value) for value in raw_cache.values())
        ),
        "oriented_schur_bytes": int(
            sum(_retained_array_bytes(value) for value in schur_cache.values())
        ),
        "scope": "assembly-time peak components; raw/oriented arrays are released after return",
    }
    retained_cache_bytes_sum = {
        key: int(comm.allreduce(value, op=MPI.SUM))
        for key, value in retained_cache_bytes_local.items()
    }
    retained_cache_bytes_max = {
        key: int(comm.allreduce(value, op=MPI.MAX))
        for key, value in retained_cache_bytes_local.items()
    }
    assembly_temporary_bytes_sum = {
        key: int(comm.allreduce(value, op=MPI.SUM))
        for key, value in assembly_temporary_bytes_local.items()
        if key != "scope"
    }
    assembly_temporary_bytes_max = {
        key: int(comm.allreduce(value, op=MPI.MAX))
        for key, value in assembly_temporary_bytes_local.items()
        if key != "scope"
    }
    return AssemblyTimeCondensedSystem(
        matrix=condensed,
        owned_trace_original_dofs=owned_trace,
        original_to_trace=mapping,
        trace_constraints=trace_constraints,
        cell_recovery_maps=tuple(recovery_maps),
        interior_from_trace_by_class=recovery_cache,
        interior_lu_by_class=lu_cache,
        interior_rhs_projection_by_class=rhs_projection_cache,
        interior_solution_embedding_by_class=solution_embedding_cache,
        trace_from_interior_rhs_by_class=rhs_trace_cache,
        interior_residual_projection_by_class=residual_projection_cache,
        full_rows=full_rows,
        trace_rows=trace_rows,
        active_rows=active_rows,
        appended_rows=appended_global_rows,
        interior_rows=interior_rows,
        active_interior_rows=active_interior_rows,
        comm=comm,
        owned_active_rows=len(owned_active),
        owned_appended_rows=local_appended,
        retained_local_schur_by_class=(
            MappingProxyType(schur_cache)
            if retain_local_schur_for_matrix_free
            else None
        ),
        build_audit={
            "schema_version": "task035b.assembly-time-cell-condensation.v1",
            "status": "unconstrained_trace_schur_built_without_full_matrix",
            "full_rows": full_rows,
            "trace_rows": trace_rows,
            "active_rows": active_rows,
            "appended_rows": appended_global_rows,
            "matrix_rows": matrix_rows,
            "matrix_materialized": materialize_global_matrix,
            "global_active_F_allocated": materialize_global_matrix,
            "trace_preallocation_status": (
                "executed" if materialize_global_matrix else "not_run_action_only"
            ),
            "trace_insertion_status": (
                "executed" if materialize_global_matrix else "not_run_action_only"
            ),
            "final_assembly_status": (
                "deferred"
                if materialize_global_matrix and defer_final_assembly
                else "executed"
                if materialize_global_matrix
                else "not_run_action_only"
            ),
            "interior_rows": interior_rows,
            "owned_cell_count_global": global_cells,
            "local_tensor_dimension": dimension,
            "local_trace_dimension": int(len(trace_positions)),
            "local_interior_dimension": int(len(interior_positions)),
            "active_cell_interior_modes": int(active_interior_rows),
            "active_full3d_equivalent_dofs": int(trace_rows + active_interior_rows),
            "storage_function_space_dofs": int(full_rows),
            "inactive_max_p_rows_retained_in_matrix": False,
            "full_global_matrix_allocated": False,
            "full_trace_matrix_allocated": False,
            "embedded_mpc_slave_identity_rows_allocated": False,
            "assembly_cost_avoided": True,
            "final_matrix_assembly_deferred_for_appended_rows": bool(
                materialize_global_matrix and defer_final_assembly
            ),
            "dense_appended_block": bool(dense_appended_block),
            "sum_duplicate_cell_integrals": bool(sum_duplicate_cell_integrals),
            "strict_local_checks": bool(strict_local_checks),
            "local_lu_identity_relative_residual_max": float(
                comm.allreduce(local_lu_residual_max, op=MPI.MAX)
            ),
            "axis_aligned_affine_geometry_verified": raw_tensor_evaluator is None,
            "preserve_exact_geometry": bool(preserve_exact_geometry),
            "geometry_policy": geometry_policy,
            "geometry_form_identity": exact_form_identity,
            "geometry_material_identity_by_tag": dict(geometry_material_identity_by_tag or {}),
            **(
                {
                    "raw_tensor_evaluator_implementation": str(
                        raw_tensor_evaluator.identity
                    ),
                    "raw_tensor_evaluator_identity": _raw_tensor_evaluator_cache_identity(
                        raw_tensor_evaluator
                    ),
                }
                if raw_tensor_evaluator is not None
                else {}
            ),
            "geometry_material_sha256_by_tag": dict(exact_material_hashes),
            "mesh_actual_exact_raw_key_count": (
                len(exact_coordinate_bytes)
                if geometry_policy == "mesh_actual_exact"
                else None
            ),
            "mesh_actual_exact_oriented_key_count": (
                len(exact_class_descriptors)
                if geometry_policy == "mesh_actual_exact"
                else None
            ),
            "mesh_actual_exact_prefix_records": (
                list(exact_probe_records)
                if geometry_policy == "mesh_actual_exact"
                else None
            ),
            "mesh_actual_exact_full_admission_passed": (
                bool(exact_full_admission_passed)
                if geometry_policy == "mesh_actual_exact"
                else None
            ),
            "geometry_identity_policy": (
                "mesh_actual_exact_coordinate_bytes"
                if geometry_policy == "mesh_actual_exact"
                else "exact_mesh_widths"
                if preserve_exact_geometry
                else "legacy_rounded_12_decimal_widths"
            ),
            "retained_local_schur_enabled": bool(retain_local_schur_for_matrix_free),
            "retained_local_schur_class_count_local": retained_class_count_local,
            "retained_local_schur_class_count_sum": retained_class_count_sum,
            "retained_local_schur_bytes_local": retained_bytes_local,
            "retained_local_schur_bytes_sum": retained_bytes_sum,
            "identity_cache_mode": (
                "shared_read_only_per_interior_shape"
                if share_identity_cache
                else "per_oriented_class"
            ),
            "identity_cache_readonly": bool(share_identity_cache),
            "identity_cache_class_count_local": (
                1 if share_identity_cache and len(schur_cache) else len(schur_cache)
            ),
            "identity_cache_bytes_local": int(
                0
                if not schur_cache
                else len(interior_positions) ** 2 * np.dtype(np.float64).itemsize
                if share_identity_cache
                else len(schur_cache)
                * len(interior_positions) ** 2
                * np.dtype(np.float64).itemsize
            ),
            **raw_cache_audit,
            "operator_cache_identity": {
                "scope": "single builder invocation; no cross-form reuse",
                "key_dependencies": (
                    [
                        "material_tag_and_coefficient_identity",
                        "compiled_kernel_and_integral_identity",
                        "coordinate_shape_dtype_and_full_bytes_sha256_collision_checked",
                        "FE_layout_identity",
                        "cell_orientation",
                        *(
                            [
                                "raw_tensor_evaluator_source_table_helper_module_cache_identity"
                            ]
                            if raw_tensor_evaluator is not None
                            else []
                        ),
                    ]
                    if geometry_policy == "mesh_actual_exact"
                    else [
                        "material_tag",
                        "cell_widths_and_jacobian",
                        "cell_orientation",
                        "polynomial_degree_and_basis_hash",
                        "ufcx_integral_ids_and_kernel_counts",
                        "complex128_scalar_type",
                    ]
                ),
                "policy_signatures": raw_cache_audit.get(
                    "raw_tensor_policy_signatures", {}
                ),
            },
            "assembly_temporary_cache_bytes_local": assembly_temporary_bytes_local,
            "assembly_temporary_cache_bytes_sum": assembly_temporary_bytes_sum,
            "assembly_temporary_cache_bytes_max": assembly_temporary_bytes_max,
            "retained_numeric_cache_bytes_local": retained_cache_bytes_local,
            "retained_numeric_cache_bytes_sum": retained_cache_bytes_sum,
            "retained_numeric_cache_bytes_max": retained_cache_bytes_max,
            "oriented_schur_class_count_sum": oriented_class_count,
            **({"action_only_complete_tensor_identities": action_tensor_identities}
               if not materialize_global_matrix else {}),
            "cell_kernel_evaluation_fraction": float(
                raw_class_count / max(global_cells, 1)
            ),
            "kernel_seconds_max": float(
                comm.allreduce(local_kernel_seconds, op=MPI.MAX)
            ),
            "local_schur_seconds_max": float(
                comm.allreduce(local_schur_seconds, op=MPI.MAX)
            ),
            **(
                {
                    "actual_qmetric_external_phase_seconds_max": {
                        "evaluator_prepare": float(
                            comm.allreduce(evaluator_prepare_seconds, op=MPI.MAX)
                        ),
                        "orientation": float(
                            comm.allreduce(local_orientation_seconds, op=MPI.MAX)
                        ),
                        "tensor_hash": float(
                            comm.allreduce(local_tensor_hash_seconds, op=MPI.MAX)
                        ),
                        "block_extract_and_validation": float(
                            comm.allreduce(local_tensor_prepare_seconds, op=MPI.MAX)
                        ),
                        "lu_solve": float(
                            comm.allreduce(local_lu_solve_seconds, op=MPI.MAX)
                        ),
                        "schur_product": float(
                            comm.allreduce(local_schur_product_seconds, op=MPI.MAX)
                        ),
                        "observer": float(
                            comm.allreduce(local_observer_seconds, op=MPI.MAX)
                        ),
                        "raw_tensor_and_block_release": float(
                            comm.allreduce(local_release_seconds, op=MPI.MAX)
                        ),
                    },
                    "actual_qmetric_evaluator_phase_seconds_local": dict(
                        raw_cache_audit.get("raw_tensor_evaluator", {}).get(
                            "phase_seconds_by_stage", {}
                        )
                    ),
                }
                if raw_tensor_evaluator is not None
                else {}
            ),
            "local_insert_seconds_max": (
                float(comm.allreduce(local_insert_seconds, op=MPI.MAX))
                if materialize_global_matrix
                else None
            ),
            "pre_final_assembly_sync_seconds_max": (preassembly_sync_seconds),
            "final_assembly_seconds": final_assembly_seconds,
            "trace_preallocation_seconds": preallocation_audit["build_seconds"],
            "trace_preallocation": preallocation_audit,
            "trace_constraints": trace_constraints.build_audit,
            "compact_action_only_maps": compact_map_preflight,
            "total_build_seconds": float(
                comm.allreduce(perf_counter() - started, op=MPI.MAX)
            ),
        },
    )


def _add_original_trace_values(
    target: PETSc.Vec,
    constraints: TraceConstraintMap,
    original_rows: np.ndarray,
    values: np.ndarray,
) -> None:
    """Accumulate ``C_t^H values`` into an independent-trace vector."""

    for original, value in zip(original_rows, values, strict=True):
        if value == 0.0:
            continue
        expansion = constraints.expansion_by_original.get(int(original))
        if expansion is None:
            raise ValueError(
                "trace projection received a cell-interior or unknown row: "
                f"{int(original)}"
            )
        active_ids, coefficients = expansion
        target.setValues(
            active_ids,
            np.asarray(
                np.conj(coefficients) * value,
                dtype=PETSc.ScalarType,
            ),
            addv=PETSc.InsertMode.ADD_VALUES,
        )


def condense_unconstrained_vector_to_active_trace(
    condensed: AssemblyTimeCondensedSystem,
    full_vector: PETSc.Vec,
    *,
    side: str,
    relative_tolerance: float = 1.0e-14,
) -> PETSc.Vec:
    """Apply the cell Schur and Floquet reductions to a full FE vector.

    ``side='right'`` computes
    ``C_t^H (b_t - A_ti A_ii^{-1} b_i)`` for a load or auxiliary
    column. ``side='left'`` returns the column representation of a reduced
    row functional,
    ``C_t^H (l_t - A_it^H A_ii^{-H} l_i)``.

    The input must be assembled in the original unconstrained FE numbering.
    Boundary forms may have nonzero cell-interior entries at high order, so
    merely dropping interior rows is not algebraically valid.
    """

    if side not in {"right", "left"}:
        raise ValueError("vector condensation side must be 'right' or 'left'")
    if full_vector.getSize() != condensed.full_rows:
        raise ValueError("full vector size differs from the FE space")
    row_start, row_end = map(int, full_vector.getOwnershipRange())
    owned_values = np.asarray(
        full_vector.getArray(readonly=True),
        dtype=np.complex128,
    )
    cutoff = max(
        1.0e-30,
        float(relative_tolerance) * float(np.max(np.abs(owned_values), initial=0.0)),
    )
    active = condensed.create_augmented_vector()
    owned_trace = condensed.owned_trace_original_dofs
    if len(owned_trace):
        trace_values = owned_values[np.asarray(owned_trace, dtype=np.int64) - row_start]
        nonzero = np.abs(trace_values) > cutoff
        _add_original_trace_values(
            active,
            condensed.trace_constraints,
            owned_trace[nonzero],
            trace_values[nonzero],
        )

    for cell in condensed.cell_recovery_maps:
        interior_rows = np.asarray(
            cell.interior_original_dofs,
            dtype=np.int64,
        )
        if len(interior_rows) and (
            int(interior_rows.min()) < row_start or int(interior_rows.max()) >= row_end
        ):
            active.destroy()
            raise ValueError(
                "owned cell-interior vector rows are outside local ownership"
            )
        interior_values = owned_values[interior_rows - row_start]
        if float(np.max(np.abs(interior_values), initial=0.0)) <= cutoff:
            continue
        if side == "right":
            correction = (
                condensed.trace_from_interior_rhs_by_class[cell.class_key]
                @ interior_values
            )
        else:
            correction = (
                condensed.interior_from_trace_by_class[cell.class_key].conj().T
                @ interior_values
            )
        nonzero = np.abs(correction) > cutoff
        _add_original_trace_values(
            active,
            condensed.trace_constraints,
            cell.trace_original_dofs[nonzero],
            correction[nonzero],
        )
    active.assemble()
    return active


def cell_interior_schur_bilinear(
    condensed: AssemblyTimeCondensedSystem,
    left_vector: PETSc.Vec,
    right_vector: PETSc.Vec,
) -> complex:
    """Return ``sum_K left_i(K)^H A_ii(K)^{-1} right_i(K)``."""

    if (
        left_vector.getSize() != condensed.full_rows
        or right_vector.getSize() != condensed.full_rows
    ):
        raise ValueError("Schur bilinear vectors differ from the FE space")
    left_start, left_end = map(int, left_vector.getOwnershipRange())
    right_start, right_end = map(int, right_vector.getOwnershipRange())
    if (left_start, left_end) != (right_start, right_end):
        raise ValueError("Schur bilinear vector ownership ranges disagree")
    left = np.asarray(
        left_vector.getArray(readonly=True),
        dtype=np.complex128,
    )
    right = np.asarray(
        right_vector.getArray(readonly=True),
        dtype=np.complex128,
    )
    local = 0.0 + 0.0j
    for cell in condensed.cell_recovery_maps:
        rows = np.asarray(cell.interior_original_dofs, dtype=np.int64)
        if len(rows) and (int(rows.min()) < left_start or int(rows.max()) >= left_end):
            raise ValueError(
                "owned cell-interior bilinear rows are outside local ownership"
            )
        local_rows = rows - left_start
        left_values = left[local_rows]
        right_values = right[local_rows]
        if not np.any(left_values) or not np.any(right_values):
            continue
        projection = condensed.interior_rhs_projection_by_class[cell.class_key]
        projected_left = projection @ left_values
        projected_right = projection @ right_values
        local += np.vdot(
            projected_left,
            lu_solve(
                condensed.interior_lu_by_class[cell.class_key],
                projected_right,
            ),
        )
    return complex(
        condensed.comm.allreduce(
            local,
            op=MPI.SUM,
        )
    )


def owned_active_support_groups(
    condensed: AssemblyTimeCondensedSystem,
    owned_cell_groups: tuple[np.ndarray, ...],
) -> tuple[np.ndarray, ...]:
    """Return owner-local active support for each group of owned cells."""

    counts = condensed.comm.allgather(condensed.owned_active_rows)
    active_start = int(sum(counts[: condensed.comm.rank]))
    active_end = active_start + condensed.owned_active_rows
    supports = []
    for cell_group in owned_cell_groups:
        active_ids: set[int] = set()
        for cell_index in np.asarray(cell_group, dtype=np.int64):
            original = condensed.cell_recovery_maps[int(cell_index)].trace_original_dofs
            ids, _expansion, _identity = _cell_trace_expansion(
                original,
                condensed.trace_constraints,
            )
            active_ids.update(map(int, ids))
        supports.append(
            np.asarray(
                [
                    active
                    for active in sorted(active_ids)
                    if active_start <= active < active_end
                ],
                dtype=PETSc.IntType,
            )
        )
    return tuple(supports)


def recover_owned_cell_interiors(
    condensed: AssemblyTimeCondensedSystem,
    active_trace_values: np.ndarray,
    *,
    full_rhs: PETSc.Vec | None = None,
) -> tuple[tuple[np.ndarray, np.ndarray], ...]:
    """Return ``(original interior DoFs, values)`` for locally owned cells."""

    active = np.asarray(active_trace_values, dtype=np.complex128)
    if active.shape != (condensed.active_rows,):
        raise ValueError("active trace value array has the wrong global length")
    rhs_values = None
    rhs_start = 0
    rhs_end = 0
    if full_rhs is not None:
        if full_rhs.getSize() != condensed.full_rows:
            raise ValueError("full recovery RHS differs from the FE space")
        rhs_start, rhs_end = map(int, full_rhs.getOwnershipRange())
        rhs_values = np.asarray(
            full_rhs.getArray(readonly=True),
            dtype=np.complex128,
        )
    result: list[tuple[np.ndarray, np.ndarray]] = []
    for cell in condensed.cell_recovery_maps:
        recovery = condensed.interior_from_trace_by_class[cell.class_key]
        local_trace = np.empty(
            len(cell.trace_original_dofs),
            dtype=np.complex128,
        )
        for row, original in enumerate(cell.trace_original_dofs):
            active_ids, coefficients = (
                condensed.trace_constraints.expansion_by_original[int(original)]
            )
            local_trace[row] = np.dot(
                coefficients,
                active[active_ids],
            )
        values = recovery @ local_trace
        if rhs_values is not None:
            rows = np.asarray(cell.interior_original_dofs, dtype=np.int64)
            if len(rows) and (
                int(rows.min()) < rhs_start or int(rows.max()) >= rhs_end
            ):
                raise ValueError(
                    "owned cell-interior recovery RHS rows are outside local ownership"
                )
            values = values + condensed.interior_solution_embedding_by_class[
                cell.class_key
            ] @ lu_solve(
                condensed.interior_lu_by_class[cell.class_key],
                condensed.interior_rhs_projection_by_class[cell.class_key]
                @ rhs_values[rows - rhs_start],
            )
        result.append((cell.interior_original_dofs, values))
    return tuple(result)


def project_mpc_vector_to_active_trace(
    condensed: AssemblyTimeCondensedSystem,
    full_vector: PETSc.Vec,
    *,
    eliminated_tolerance: float = 1.0e-12,
    eliminated_relative_tolerance: float = (1024.0 * np.finfo(np.float64).eps),
    audit: dict[str, object] | None = None,
) -> PETSc.Vec:
    """Project an already MPC-assembled full-space vector to active trace rows.

    ``dolfinx_mpc.assemble_vector`` has already applied ``C^H`` and leaves
    slave entries at zero.  This function verifies that no eliminated
    cell-interior or slave entry is nonzero before physically dropping them.
    MPC slave entries must be exactly zero because constraint assembly has
    already applied ``C^H``.  Cell-interior entries use the larger of the
    requested absolute floor and a global retained-signal roundoff envelope.
    This keeps high-order tangential-form audits invariant under harmless mode
    normalization while leaving the slave contract exact.
    """

    if full_vector.getSize() != condensed.full_rows:
        raise ValueError("full MPC vector size differs from the FE space")
    if (
        not np.isfinite(eliminated_tolerance)
        or not np.isfinite(eliminated_relative_tolerance)
        or eliminated_tolerance < 0.0
        or eliminated_relative_tolerance < 0.0
    ):
        raise ValueError("eliminated-vector tolerances must be finite and nonnegative")
    comm = condensed.comm
    row_start, row_end = full_vector.getOwnershipRange()
    owned_original = np.arange(row_start, row_end, dtype=PETSc.IntType)
    owned_values = np.asarray(
        full_vector.getArray(readonly=True),
        dtype=np.complex128,
    )
    nonfinite_count = int(
        comm.allreduce(
            int(np.count_nonzero(~np.isfinite(owned_values))),
            op=MPI.SUM,
        )
    )
    if nonfinite_count:
        raise ValueError(
            "MPC vector contains nonfinite entries before trace projection: "
            f"global_count={nonfinite_count}"
        )
    active_set = set(
        int(value) for value in condensed.trace_constraints.owned_active_original_dofs
    )
    trace_set = set(int(value) for value in condensed.owned_trace_original_dofs)
    active_mask = np.asarray(
        [int(row) in active_set for row in owned_original],
        dtype=bool,
    )
    slave_mask = np.asarray(
        [
            int(row) in trace_set and int(row) not in active_set
            for row in owned_original
        ],
        dtype=bool,
    )
    interior_mask = np.asarray(
        [int(row) not in trace_set for row in owned_original],
        dtype=bool,
    )

    def global_max(mask: np.ndarray) -> float:
        local = float(np.max(np.abs(owned_values[mask]), initial=0.0))
        return float(comm.allreduce(local, op=MPI.MAX))

    max_active = global_max(active_mask)
    max_slave = global_max(slave_mask)
    max_interior = global_max(interior_mask)
    slave_cutoff = 0.0
    interior_cutoff = max(
        float(eliminated_tolerance),
        float(eliminated_relative_tolerance) * max_active,
    )
    interior_roundoff_units = (
        max_interior / (float(np.finfo(np.float64).eps) * max_active)
        if max_active > 0.0
        else float("inf")
    )
    offending_mask = (slave_mask & (np.abs(owned_values) > slave_cutoff)) | (
        interior_mask & (np.abs(owned_values) > interior_cutoff)
    )
    local_first = int(
        np.min(owned_original[offending_mask], initial=condensed.full_rows)
    )
    first_offending_dof = int(comm.allreduce(local_first, op=MPI.MIN))
    if first_offending_dof >= condensed.full_rows:
        first_offending_dof = -1
        first_offending_entity = None
    else:
        local_entity_code = 0
        local_match = np.flatnonzero(owned_original == first_offending_dof)
        if len(local_match):
            first_index = int(local_match[0])
            if bool(slave_mask[first_index]):
                local_entity_code = 1
            elif bool(interior_mask[first_index]):
                local_entity_code = 2
        entity_code = int(comm.allreduce(local_entity_code, op=MPI.MAX))
        first_offending_entity = {
            1: "floquet_slave_trace",
            2: "cell_interior",
        }.get(entity_code, "unknown")
    if audit is not None:
        audit.update(
            {
                "max_active": max_active,
                "max_slave": max_slave,
                "max_cell_interior": max_interior,
                "slave_absolute_cutoff": slave_cutoff,
                "cell_interior_cutoff": interior_cutoff,
                "eliminated_relative_tolerance": float(eliminated_relative_tolerance),
                "cell_interior_roundoff_units": interior_roundoff_units,
                "first_offending_dof": first_offending_dof,
                "first_offending_entity": first_offending_entity,
                "pass": bool(
                    max_slave <= slave_cutoff and max_interior <= interior_cutoff
                ),
            }
        )
    if max_slave > slave_cutoff or max_interior > interior_cutoff:
        raise ValueError(
            "MPC vector has nonzero eliminated interior/slave entries: "
            f"slave_cutoff={slave_cutoff:.3e}, "
            f"interior_cutoff={interior_cutoff:.3e}, "
            f"active_scale={max_active:.3e}, slave={max_slave:.3e}, "
            f"interior={max_interior:.3e}, "
            f"interior_roundoff_units={interior_roundoff_units:.3e}, "
            f"first_offending_dof={first_offending_dof}, "
            f"first_offending_entity={first_offending_entity}"
        )
    active_vector = condensed.create_augmented_vector()
    active_original = condensed.trace_constraints.owned_active_original_dofs
    if len(active_original):
        active_vector.getArray()[: len(active_original)] = np.asarray(
            full_vector.getValues(active_original),
            dtype=PETSc.ScalarType,
        )
    active_vector.assemble()
    return active_vector


__all__ = [
    "AssemblyTimeCondensedSystem",
    "CellRecoveryMap",
    "TraceConstraintMap",
    "build_unconstrained_assembly_time_condensation",
    "cell_interior_schur_bilinear",
    "condense_unconstrained_vector_to_active_trace",
    "owned_active_support_groups",
    "project_mpc_vector_to_active_trace",
    "recover_owned_cell_interiors",
]
