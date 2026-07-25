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

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy import sparse
from scipy.linalg import lu_factor, lu_solve


def _idx(values) -> np.ndarray:
    if isinstance(values, np.ndarray):
        return np.asarray(values, dtype=PETSc.IntType)
    return np.fromiter(values, dtype=PETSc.IntType)


@dataclass(frozen=True)
class CellRecoveryMap:
    """Numbering and cached class identity needed for one owned cell."""

    interior_original_dofs: np.ndarray
    trace_original_dofs: np.ndarray
    cell_local_dofs: np.ndarray
    raw_key: tuple[Any, ...]
    cell_permutation: int
    interior_policy: str
    class_key: tuple[Any, ...]


@dataclass(frozen=True)
class TraceConstraintMap:
    """Sparse full-trace to independent-trace expansion ``u_t = C_t q``."""

    owned_active_original_dofs: np.ndarray
    original_to_active: dict[int, int]
    expansion_by_original: dict[int, tuple[np.ndarray, np.ndarray]]
    full_trace_rows: int
    active_rows: int
    slave_rows: int
    build_audit: dict[str, Any]


@dataclass
class AssemblyTimeCondensedSystem:
    """Physically reduced trace matrix and matrix-free recovery metadata."""

    matrix: PETSc.Mat
    owned_trace_original_dofs: np.ndarray
    original_to_trace: dict[int, int]
    trace_constraints: TraceConstraintMap
    cell_recovery_maps: tuple[CellRecoveryMap, ...]
    interior_from_trace_by_class: dict[tuple[Any, ...], np.ndarray]
    interior_lu_by_class: dict[
        tuple[Any, ...], tuple[np.ndarray, np.ndarray]
    ]
    interior_rhs_projection_by_class: dict[
        tuple[Any, ...], np.ndarray
    ]
    interior_solution_embedding_by_class: dict[
        tuple[Any, ...], np.ndarray
    ]
    dual_interior_from_trace_by_class: dict[
        tuple[Any, ...], np.ndarray
    ]
    appended_dual_interior_by_cell: tuple[
        dict[int, np.ndarray], ...
    ]
    appended_dual_rows_registered: set[int]
    trace_from_interior_rhs_by_class: dict[tuple[Any, ...], np.ndarray]
    interior_residual_projection_by_class: dict[
        tuple[Any, ...], np.ndarray
    ]
    full_rows: int
    trace_rows: int
    active_rows: int
    appended_rows: int
    interior_rows: int
    active_interior_rows: int
    build_audit: dict[str, Any]
    affine_isotropic_tensor_spec: Any | None = None

    def destroy(self) -> None:
        self.matrix.destroy()


def _owned_trace_numbering(
    function_space,
    local_cell_interior_dofs: tuple[np.ndarray, ...],
) -> tuple[np.ndarray, dict[int, int], int, int]:
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
        int(local_interior.min()) < full_start
        or int(local_interior.max()) >= full_end
    ):
        raise ValueError("owned cell-interior DoFs must be owned by the cell rank")
    owned_full = np.arange(full_start, full_end, dtype=PETSc.IntType)
    owned_trace = owned_full[
        ~np.isin(owned_full, local_interior, assume_unique=True)
    ]
    counts = comm.allgather(int(len(owned_trace)))
    trace_start = int(sum(counts[: comm.rank]))
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
    mapping: dict[int, int] = {}
    for originals, traces in packets:
        mapping.update(
            (int(original), int(trace))
            for original, trace in zip(originals, traces, strict=True)
        )
    trace_rows = int(sum(counts))
    full_rows = int(index_map.size_global * dofmap.index_map_bs)
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


def _cell_integral_kernels(compiled_form) -> dict[int, Any]:
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
) -> TraceConstraintMap:
    """Build an exact distributed trace-only MPC expansion.

    The finalized ``dolfinx_mpc`` object stores master links in its augmented
    local numbering.  Constraint rows are gathered once because a locally
    owned cell may touch a trace slave owned by another rank.
    """

    comm = function_space.mesh.comm
    index_map = function_space.dofmap.index_map
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
    global_slave_original = {
        int(value) for packet in slave_packets for value in packet
    }
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
    owned_constraint_rows: list[
        tuple[int, np.ndarray, np.ndarray]
    ] = []
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
                    "MPC trace row references non-trace masters: "
                    f"{missing_masters[:8]}"
                )
            active_ids = _idx(
                original_to_active[int(master)] for master in masters
            )
            expansion[int(slave)] = (
                active_ids,
                np.asarray(row_coefficients, dtype=np.complex128),
            )
            maximum_masters = max(maximum_masters, len(active_ids))
    missing_expansion = set(original_to_trace) - set(expansion)
    if missing_expansion:
        raise RuntimeError(
            "trace constraint expansion is incomplete: "
            f"{sorted(missing_expansion)[:8]}"
        )
    return TraceConstraintMap(
        owned_active_original_dofs=owned_active,
        original_to_active=original_to_active,
        expansion_by_original=expansion,
        full_trace_rows=trace_rows,
        active_rows=active_rows,
        slave_rows=slave_rows,
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

    active_blocks = [
        constraints.expansion_by_original[int(original)]
        for original in trace_original
    ]
    unique_active = _idx(
        sorted(
            {
                int(active)
                for ids, _coefficients in active_blocks
                for active in ids
            }
        )
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
        if all(
            error is None or error.startswith("ValueError:")
            for error in errors
        )
        else TypeError
        if all(
            error is None or error.startswith("TypeError:")
            for error in errors
        )
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
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Build exact base and support-safe appended AIJ preallocation."""

    local_validation_error = None
    local_contract = None
    try:
        normalized_active_counts = tuple(
            int(count) for count in active_counts
        )
        normalized_appended_rows = int(appended_global_rows)
        normalized_group_by_row = tuple(
            int(group) for group in appended_support_group_by_row
        )
        if len(normalized_active_counts) != comm.size:
            raise ValueError(
                "active row counts do not match the MPI communicator"
            )
        if any(count < 0 for count in normalized_active_counts):
            raise ValueError("active row counts must be nonnegative")
        if normalized_appended_rows < 0:
            raise ValueError("appended row count must be nonnegative")
        active_rows_for_validation = int(sum(normalized_active_counts))
        for ids in cell_active_ids:
            active = np.asarray(ids, dtype=np.int64)
            if len(active) == 0:
                raise ValueError(
                    "a cell has no active constrained trace rows"
                )
            if (
                int(active.min()) < 0
                or int(active.max()) >= active_rows_for_validation
            ):
                raise ValueError(
                    "a cell contains an out-of-range active trace row"
                )
        if normalized_appended_rows == 0:
            if (
                appended_support_owned_cell_groups
                or normalized_group_by_row
            ):
                raise ValueError(
                    "appended support was provided without appended rows"
                )
        elif (
            len(normalized_group_by_row) != normalized_appended_rows
            or not appended_support_owned_cell_groups
        ):
            raise ValueError(
                "every appended row requires an explicit support group"
            )
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
                int(cells.min()) < 0
                or int(cells.max()) >= len(cell_active_ids)
            ):
                raise ValueError(
                    "appended support group contains a non-owned cell"
                )
        local_contract = (
            normalized_active_counts,
            normalized_appended_rows,
            group_count,
            normalized_group_by_row,
        )
    except Exception as error:
        local_validation_error = f"{type(error).__name__}: {error}"
    validation_packets = comm.allgather(
        (local_validation_error, local_contract)
    )
    _collective_preallocation_error(
        [packet[0] for packet in validation_packets],
        context="trace preallocation input validation failed",
    )
    contracts = [packet[1] for packet in validation_packets]
    if any(contract != contracts[0] for contract in contracts[1:]):
        raise RuntimeError(
            "trace preallocation contract differs across MPI ranks"
        )
    assert local_contract is not None
    (
        normalized_active_counts,
        normalized_appended_rows,
        _group_count,
        normalized_group_by_row,
    ) = local_contract
    active_offsets = np.concatenate(
        (
            np.asarray([0], dtype=np.int64),
            np.cumsum(
                np.asarray(normalized_active_counts, dtype=np.int64)
            ),
        )
    )
    active_rows = int(active_offsets[-1])
    local_active_start = int(active_offsets[comm.rank])
    local_active_end = int(active_offsets[comm.rank + 1])
    local_active_rows = local_active_end - local_active_start
    local_appended_rows = (
        normalized_appended_rows if comm.rank == comm.size - 1 else 0
    )
    local_rows = local_active_rows + local_appended_rows
    local_end = local_active_start + local_rows

    send_packets: list[list[np.ndarray]] = [
        [] for _rank in range(comm.size)
    ]
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
    incident: list[list[np.ndarray]] = [
        [] for _row in range(local_active_rows)
    ]
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
        appended_columns = (
            active_rows + appended_indices
        ).astype(PETSc.IntType)
        group_rows.append(appended_columns)
        local_support = support[
            (support >= local_active_start)
            & (support < local_active_end)
        ]
        for row in local_support:
            appended_columns_by_local_active[
                int(row) - local_active_start
            ].append(appended_columns)

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
                    (columns >= local_active_start)
                    & (columns < local_end)
                )
            )
            diagonal_nnz[local_row] = diagonal
            off_diagonal_nnz[local_row] = len(columns) - diagonal
            structural_nnz_local += len(columns)

        if local_appended_rows:
            for appended_index in range(normalized_appended_rows):
                local_row = local_active_rows + appended_index
                group = normalized_group_by_row[appended_index]
                columns = np.unique(
                    np.concatenate(
                        (
                            support_groups[group],
                            np.asarray(
                                [active_rows + appended_index],
                                dtype=PETSc.IntType,
                            ),
                        )
                    )
                )
                diagonal = int(
                    np.count_nonzero(
                        (columns >= local_active_start)
                        & (columns < local_end)
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

    preallocated_nnz = int(
        comm.allreduce(structural_nnz_local, op=MPI.SUM)
    )
    return diagonal_nnz, off_diagonal_nnz, {
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
        "appended_rows_per_support_group": [
            int(len(rows)) for rows in group_rows
        ],
        "new_nonzero_allocation_error_enabled": True,
        "ordinary_default_changed": False,
    }


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
    return np.ascontiguousarray(
        expansion.transpose().dot(left.transpose()).transpose()
    )


def _python_visible_native_array_ledger(
    comm,
    categories: Mapping[str, Any],
    *,
    transient_categories: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Count unique NumPy backing stores visible at the build-return boundary."""

    seen: set[int] = set()
    local_bytes: dict[str, int] = {}

    def visit(value: Any, category: str) -> None:
        if isinstance(value, np.ndarray):
            storage = value
            while isinstance(storage.base, np.ndarray):
                storage = storage.base
            identity = id(storage)
            if identity not in seen:
                seen.add(identity)
                local_bytes[category] = (
                    local_bytes.get(category, 0)
                    + int(storage.nbytes)
                )
            return
        if isinstance(value, Mapping):
            for item in value.values():
                visit(item, category)
            return
        if isinstance(value, (tuple, list)):
            for item in value:
                visit(item, category)

    for category, values in categories.items():
        local_bytes[str(category)] = 0
        visit(values, str(category))
    rank_sum_bytes = {
        category: int(comm.allreduce(value, op=MPI.SUM))
        for category, value in local_bytes.items()
    }
    rank_max_bytes = {
        category: int(comm.allreduce(value, op=MPI.MAX))
        for category, value in local_bytes.items()
    }
    local_total = int(sum(local_bytes.values()))
    transient = {str(value) for value in transient_categories}
    retained_local_total = int(
        sum(
            value
            for category, value in local_bytes.items()
            if category not in transient
        )
    )
    return {
        "schema_version": (
            "task035b.condensation-native-object-ledger.v1"
        ),
        "measurement": "unique_numpy_backing_store_nbytes",
        "rank_local_bytes": local_bytes,
        "rank_sum_bytes": rank_sum_bytes,
        "rank_max_bytes": rank_max_bytes,
        "rank_local_total_bytes": local_total,
        "rank_sum_total_bytes": int(
            comm.allreduce(local_total, op=MPI.SUM)
        ),
        "rank_max_total_bytes": int(
            comm.allreduce(local_total, op=MPI.MAX)
        ),
        "transient_categories_released_after_build": sorted(transient),
        "retained_rank_local_total_bytes": retained_local_total,
        "retained_rank_sum_total_bytes": int(
            comm.allreduce(retained_local_total, op=MPI.SUM)
        ),
        "retained_rank_max_total_bytes": int(
            comm.allreduce(retained_local_total, op=MPI.MAX)
        ),
        "excluded_objects": [
            "PETSc Mat and Vec native allocations",
            "KSP, preconditioner, and MUMPS allocations",
            "DOLFINx and Basix C++ object storage",
            "Python container and allocator overhead",
            "temporary BLAS and LAPACK workspaces",
        ],
        "scope_not_claimed_as_process_memory": True,
        "ordinary_default_changed": False,
    }


class _DenseBlockBatchInserter:
    """Insert many dense cell blocks through bounded PETSc IJV payloads."""

    def __init__(
        self,
        matrix: PETSc.Mat,
        *,
        maximum_payload_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        if maximum_payload_bytes <= 0:
            raise ValueError("maximum_payload_bytes must be positive")
        self._matrix = matrix
        self._maximum_payload_bytes = int(maximum_payload_bytes)
        self._rows: list[np.ndarray] = []
        self._values: list[np.ndarray] = []
        self._pending_payload_bytes = 0
        self.call_count = 0
        self.cell_block_count = 0
        self.scalar_entry_count = 0
        self.peak_payload_bytes = 0

    def add(self, rows: np.ndarray, values: np.ndarray) -> None:
        row_ids = np.asarray(rows, dtype=PETSc.IntType)
        block = np.asarray(values, dtype=PETSc.ScalarType)
        if block.shape != (len(row_ids), len(row_ids)):
            raise ValueError("batched cell block must be square on its row IDs")
        payload_bytes = int(
            row_ids.nbytes
            + block.nbytes
            + row_ids.nbytes * len(row_ids)
        )
        if (
            self._rows
            and self._pending_payload_bytes + payload_bytes
            > self._maximum_payload_bytes
        ):
            self.flush()
        self._rows.append(row_ids.copy())
        self._values.append(np.ascontiguousarray(block))
        self._pending_payload_bytes += payload_bytes
        self.cell_block_count += 1
        self.scalar_entry_count += int(block.size)
        if self._pending_payload_bytes >= self._maximum_payload_bytes:
            self.flush()

    def flush(self) -> None:
        if not self._rows:
            return
        row_map = np.concatenate(self._rows).astype(
            PETSc.IntType,
            copy=False,
        )
        row_lengths = np.concatenate(
            [
                np.full(len(rows), len(rows), dtype=PETSc.IntType)
                for rows in self._rows
            ]
        )
        row_pointer = np.empty(len(row_map) + 1, dtype=PETSc.IntType)
        row_pointer[0] = 0
        np.cumsum(row_lengths, out=row_pointer[1:])
        columns = np.concatenate(
            [
                np.tile(rows, len(rows)).astype(
                    PETSc.IntType,
                    copy=False,
                )
                for rows in self._rows
            ]
        )
        values = np.concatenate(
            [block.reshape(-1) for block in self._values]
        ).astype(PETSc.ScalarType, copy=False)
        actual_payload_bytes = int(
            row_map.nbytes
            + row_pointer.nbytes
            + columns.nbytes
            + values.nbytes
        )
        self.peak_payload_bytes = max(
            self.peak_payload_bytes,
            actual_payload_bytes,
        )
        self._matrix.setValuesIJV(
            row_pointer,
            columns,
            values,
            addv=PETSc.InsertMode.ADD_VALUES,
            rowmap=row_map,
        )
        self.call_count += 1
        self._rows.clear()
        self._values.clear()
        self._pending_payload_bytes = 0

    def audit(self, comm) -> dict[str, Any]:
        if self._rows:
            raise RuntimeError("bulk insertion audit requires a flushed payload")
        return {
            "schema_version": "task035b.dense-cell-block-bulk-insertion.v1",
            "enabled": True,
            "backend": "petsc4py.Mat.setValuesIJV",
            "add_values_semantics": True,
            "maximum_payload_bytes": self._maximum_payload_bytes,
            "cell_block_count_global": int(
                comm.allreduce(self.cell_block_count, op=MPI.SUM)
            ),
            "scalar_entry_count_global": int(
                comm.allreduce(self.scalar_entry_count, op=MPI.SUM)
            ),
            "ijv_call_count_sum": int(
                comm.allreduce(self.call_count, op=MPI.SUM)
            ),
            "ijv_call_count_max_per_rank": int(
                comm.allreduce(self.call_count, op=MPI.MAX)
            ),
            "peak_temporary_payload_bytes_max_per_rank": int(
                comm.allreduce(self.peak_payload_bytes, op=MPI.MAX)
            ),
            "per_cell_petsc_mat_set_values_call_eliminated": True,
            "ordinary_default_changed": False,
        }


def _canonical_axis_aligned_coordinates(
    mesh,
    cell: int,
    *,
    tolerance: float,
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
    rounded_widths = tuple(float(np.round(value, 12)) for value in widths)
    for axis, width in enumerate(rounded_widths):
        canonical[canonical[:, axis] != 0.0, axis] = width
    return np.ascontiguousarray(canonical.ravel()), rounded_widths


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
    default_kernel = kernels.get(-1)
    if default_kernel is not None:
        tensor += _tabulate_cell_tensor(
            compiled_form,
            default_kernel,
            coordinates,
            dimension,
        )
    tagged_kernel = kernels.get(int(tag))
    if tagged_kernel is not None:
        tensor += _tabulate_cell_tensor(
            compiled_form,
            tagged_kernel,
            coordinates,
            dimension,
        )
    if default_kernel is None and tagged_kernel is None:
        raise ValueError(
            f"compiled form has no default or tagged kernel for tag {tag}"
        )
    return tensor


def _persistent_raw_tensor_identity(
    *,
    source_sha: str,
    policy_signature: Mapping[str, Any],
    class_key: tuple[Any, ...],
    coordinates: np.ndarray,
) -> tuple[str, dict[str, Any]]:
    payload = {
        "schema_version": "task035b.raw-tensor-persistent-cache.v1",
        "source_commit_sha": source_sha,
        "policy_signature": dict(policy_signature),
        "class_key": list(class_key),
        "canonical_coordinates_sha256": hashlib.sha256(
            np.ascontiguousarray(
                coordinates,
                dtype=np.float64,
            ).tobytes()
        ).hexdigest(),
        "scalar_dtype": str(np.dtype(np.complex128)),
        "int_dtype": str(np.dtype(PETSc.IntType)),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest(), payload


def _raw_tensor_content_sha256(tensor: np.ndarray) -> str:
    canonical = np.ascontiguousarray(
        tensor,
        dtype=np.complex128,
    )
    metadata = json.dumps(
        {
            "shape": list(canonical.shape),
            "dtype": canonical.dtype.str,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    digest = hashlib.sha256()
    digest.update(b"task035b.raw-tensor-content.v1\0")
    digest.update(metadata)
    digest.update(b"\0")
    digest.update(canonical.tobytes(order="C"))
    return digest.hexdigest()


def _load_persistent_raw_tensor(
    path: Path,
    *,
    manifest_path: Path,
    dimension: int,
    expected_identity_sha256: str,
) -> tuple[np.ndarray | None, str | None]:
    if not path.is_file() or not manifest_path.is_file():
        return None, "artifact_or_manifest_missing"
    try:
        with manifest_path.open("r", encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, "manifest_unreadable"
    if not isinstance(manifest, dict):
        return None, "manifest_not_an_object"
    if (
        manifest.get("schema_version")
        != "task035b.raw-tensor-cache-manifest.v2"
    ):
        return None, "manifest_schema_mismatch"
    if (
        manifest.get("identity_sha256")
        != expected_identity_sha256
    ):
        return None, "identity_sha256_mismatch"
    if manifest.get("payload_filename") != path.name:
        return None, "payload_filename_mismatch"
    try:
        tensor = np.load(path, allow_pickle=False)
    except (OSError, ValueError):
        return None, "payload_unreadable"
    if (
        tensor.shape != (dimension, dimension)
        or tensor.dtype != np.dtype(np.complex128)
        or not np.all(np.isfinite(tensor))
    ):
        return None, "payload_shape_dtype_or_finite_mismatch"
    tensor = np.ascontiguousarray(tensor)
    if (
        manifest.get("tensor_content_sha256")
        != _raw_tensor_content_sha256(tensor)
    ):
        return None, "payload_checksum_mismatch"
    return tensor, None


def _write_persistent_raw_tensor(
    path: Path,
    tensor: np.ndarray,
    *,
    manifest_path: Path,
    identity_sha256: str,
    identity_payload: Mapping[str, Any],
    rank: int,
) -> None:
    temporary_payload = path.with_name(
        f".{path.name}.rank{rank}.tmp"
    )
    temporary_manifest = manifest_path.with_name(
        f".{manifest_path.name}.rank{rank}.tmp"
    )
    canonical = np.ascontiguousarray(
        tensor,
        dtype=np.complex128,
    )
    try:
        with temporary_payload.open("wb") as stream:
            np.save(stream, canonical, allow_pickle=False)
            stream.flush()
            os.fsync(stream.fileno())
        manifest = {
            "schema_version": "task035b.raw-tensor-cache-manifest.v2",
            "identity_sha256": identity_sha256,
            "identity": dict(identity_payload),
            "payload_filename": path.name,
            "shape": list(canonical.shape),
            "dtype": canonical.dtype.str,
            "tensor_content_sha256": _raw_tensor_content_sha256(
                canonical
            ),
            "payload_size_bytes": int(
                temporary_payload.stat().st_size
            ),
            "pickle_used": False,
        }
        with temporary_manifest.open(
            "w",
            encoding="utf-8",
        ) as stream:
            json.dump(
                manifest,
                stream,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Publish the manifest last.  A reader either sees the previous
        # checksum pair or rejects a partial update and recomputes.
        os.replace(temporary_payload, path)
        os.replace(temporary_manifest, manifest_path)
    finally:
        for temporary in (temporary_payload, temporary_manifest):
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _global_raw_tensor_cache(
    comm,
    local_class_coordinates: dict[tuple[Any, ...], np.ndarray],
    policy_forms: dict[
        str,
        tuple[Any | None, dict[int, Any], int, Any],
    ],
    *,
    persistent_cache_directory: Path | None = None,
    persistent_cache_source_sha: str | None = None,
    persistent_cache_mode: str = "off",
    affine_isotropic_tensor_spec=None,
) -> tuple[dict[tuple[Any, ...], np.ndarray], dict[str, Any], float]:
    """Evaluate each raw tensor class once globally, then broadcast it.

    Every rank participates in the deterministic class order.  Only ranks
    owning cells in a class retain its tensor after the broadcast.
    """

    persistent_cache_mode = str(persistent_cache_mode).lower()
    if persistent_cache_mode not in {
        "off",
        "read_only",
        "read_write",
        "refresh",
    }:
        raise ValueError(
            "persistent_cache_mode must be off, read_only, read_write, "
            "or refresh"
        )
    persistent_enabled = persistent_cache_mode != "off"
    if persistent_enabled:
        source_sha = str(persistent_cache_source_sha or "").lower()
        if len(source_sha) != 40 or any(
            character not in "0123456789abcdef"
            for character in source_sha
        ):
            raise ValueError(
                "persistent raw-tensor cache requires a full source Git SHA"
            )
        if persistent_cache_directory is None:
            raise ValueError(
                "persistent raw-tensor cache requires a cache directory"
            )
        cache_directory = Path(persistent_cache_directory).resolve()
        if comm.rank == 0 and persistent_cache_mode in {
            "read_write",
            "refresh",
        }:
            cache_directory.mkdir(parents=True, exist_ok=True)
        comm.Barrier()
        if not cache_directory.is_dir():
            raise ValueError(
                "persistent raw-tensor cache directory is unavailable"
            )
    else:
        source_sha = None
        cache_directory = None

    local_policy_signature = {}
    for policy, (
        policy_compiled_form,
        kernels,
        dimension,
        policy_element,
    ) in policy_forms.items():
        signature = {
            "dimension": int(dimension),
            "kernel_ids": tuple(sorted(int(key) for key in kernels)),
            "dtype": str(
                np.dtype(np.complex128)
                if policy_compiled_form is None
                else np.dtype(policy_compiled_form.dtype)
            ),
            "element_hash": int(policy_element.hash()),
        }
        if affine_isotropic_tensor_spec is None:
            if policy_compiled_form is None:
                raise ValueError(
                    "FFCx raw tensor backend requires a compiled form"
                )
            signature["ufcx_form_signature"] = (
                policy_compiled_form.module.ffi.string(
                    policy_compiled_form.ufcx_form.signature
                ).decode("ascii")
            )
            signature["raw_tensor_backend"] = "compiled_ffcx_cell_kernel"
        else:
            signature["ufcx_form_signature"] = None
            signature["raw_tensor_backend"] = (
                "affine_isotropic_reference_gram_v1"
            )
            signature["affine_isotropic_tensor_spec"] = (
                affine_isotropic_tensor_spec.identity(policy_element)
            )
        local_policy_signature[policy] = signature
    policy_signatures = comm.allgather(local_policy_signature)
    if any(
        signature != policy_signatures[0]
        for signature in policy_signatures[1:]
    ):
        raise RuntimeError(
            "raw tensor FFCx policy signatures differ across MPI ranks"
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
                    int(-1 in policy_forms[str(value[0])][1])
                    + int(int(value[1]) in policy_forms[str(value[0])][1])
                )
            ),
            value,
        ),
    ):
        owner = (
            0
            if affine_isotropic_tensor_spec is not None
            else min(
                range(comm.size),
                key=lambda rank: (owner_loads[rank], rank),
            )
        )
        owner_by_class[key] = int(owner)
        owner_loads[owner] += (
            int(policy_forms[str(key[0])][2]) ** 2
            * (
                int(-1 in policy_forms[str(key[0])][1])
                + int(int(key[1]) in policy_forms[str(key[0])][1])
            )
        )
    cache: dict[tuple[Any, ...], np.ndarray] = {}
    local_kernel_seconds = 0.0
    local_cache_read_seconds = 0.0
    local_cache_write_seconds = 0.0
    local_broadcast_seconds = 0.0
    local_evaluations = 0
    local_cache_hits = 0
    local_cache_writes = 0
    local_cache_read_bytes = 0
    local_cache_write_bytes = 0
    local_cache_miss_reasons: dict[str, int] = {}
    local_reference_gram_seconds = 0.0
    local_analytic_combination_seconds = 0.0
    analytic_factories: dict[str, Any] = {}
    analytic_factory_audits: dict[str, dict[str, Any]] = {}
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
            compiled_form, kernels, dimension, policy_element = (
                policy_forms[policy]
            )
            cache_path = None
            if cache_directory is not None and source_sha is not None:
                digest, identity = _persistent_raw_tensor_identity(
                    source_sha=source_sha,
                    policy_signature=local_policy_signature[policy],
                    class_key=key,
                    coordinates=global_coordinates[key],
                )
                cache_path = cache_directory / f"raw_tensor_{digest}.npy"
                manifest_path = cache_path.with_suffix(".json")
                if persistent_cache_mode != "refresh":
                    cache_started = perf_counter()
                    cached, miss_reason = _load_persistent_raw_tensor(
                        cache_path,
                        manifest_path=manifest_path,
                        dimension=int(dimension),
                        expected_identity_sha256=digest,
                    )
                    local_cache_read_seconds += (
                        perf_counter() - cache_started
                    )
                    if cached is not None:
                        locally_evaluated[key] = cached
                        local_cache_hits += 1
                        local_cache_read_bytes += int(
                            cache_path.stat().st_size
                            + manifest_path.stat().st_size
                        )
                        continue
                    assert miss_reason is not None
                    local_cache_miss_reasons[miss_reason] = (
                        local_cache_miss_reasons.get(
                            miss_reason,
                            0,
                        )
                        + 1
                    )
                else:
                    local_cache_miss_reasons["refresh_forced"] = (
                        local_cache_miss_reasons.get(
                            "refresh_forced",
                            0,
                        )
                        + 1
                    )
            kernel_started = perf_counter()
            if affine_isotropic_tensor_spec is None:
                if compiled_form is None:
                    raise RuntimeError(
                        "compiled FFCx form is absent on the FFCx backend"
                    )
                locally_evaluated[key] = _tabulate_raw_tensor_class(
                    compiled_form,
                    kernels,
                    global_coordinates[key],
                    tag=int(key[1]),
                    dimension=int(dimension),
                )
            else:
                from .hcurl_affine_isotropic_tensor import (
                    AffineIsotropicMaxwellTensorFactory,
                )

                factory = analytic_factories.get(policy)
                if factory is None:
                    factory = AffineIsotropicMaxwellTensorFactory(
                        policy_element,
                        affine_isotropic_tensor_spec,
                    )
                    analytic_factories[policy] = factory
                    local_reference_gram_seconds += float(
                        factory.build_seconds
                    )
                    analytic_factory_audits[policy] = dict(
                        factory.audit
                    )
                combination_started = perf_counter()
                locally_evaluated[key] = factory.tensor(
                    tag=int(key[1]),
                    widths=tuple(float(value) for value in key[2:]),
                )
                local_analytic_combination_seconds += (
                    perf_counter() - combination_started
                )
            local_kernel_seconds += perf_counter() - kernel_started
            local_evaluations += 1
            if (
                cache_path is not None
                and persistent_cache_mode in {"read_write", "refresh"}
            ):
                cache_started = perf_counter()
                _write_persistent_raw_tensor(
                    cache_path,
                    locally_evaluated[key],
                    manifest_path=manifest_path,
                    identity_sha256=digest,
                    identity_payload=identity,
                    rank=comm.rank,
                )
                local_cache_write_seconds += (
                    perf_counter() - cache_started
                )
                local_cache_writes += 1
                local_cache_write_bytes += int(
                    cache_path.stat().st_size
                    + manifest_path.stat().st_size
                )
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
        _compiled_form, _kernels, dimension, _element = (
            policy_forms[policy]
        )
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

    evaluation_count = int(
        comm.allreduce(local_evaluations, op=MPI.SUM)
    )
    cache_hit_count = int(
        comm.allreduce(local_cache_hits, op=MPI.SUM)
    )
    cache_write_count = int(
        comm.allreduce(local_cache_writes, op=MPI.SUM)
    )
    cache_miss_reasons: dict[str, int] = {}
    for rank_reasons in comm.allgather(local_cache_miss_reasons):
        for reason, count in rank_reasons.items():
            cache_miss_reasons[reason] = (
                cache_miss_reasons.get(reason, 0) + int(count)
            )
    use_count = int(
        comm.allreduce(len(local_class_coordinates), op=MPI.SUM)
    )
    unique_count = len(global_coordinates)
    if evaluation_count + cache_hit_count != unique_count:
        raise RuntimeError(
            "raw tensor evaluation plus persistent hits does not match "
            "unique classes"
        )
    if set(cache) != local_keys:
        raise RuntimeError("global raw tensor cache is incomplete on this rank")
    return cache, {
        "raw_tensor_class_count_sum": unique_count,
        "raw_tensor_class_construction_count": evaluation_count,
        "raw_tensor_kernel_evaluation_count": evaluation_count,
        "raw_tensor_persistent_cache_hit_count": cache_hit_count,
        "raw_tensor_persistent_cache_write_count": cache_write_count,
        "raw_tensor_class_use_count_sum": use_count,
        "raw_tensor_class_count_global_unique": unique_count,
        "raw_tensor_global_owner_policy": (
            "rank0_reference_gram_then_raw_tensor_broadcast"
            if affine_isotropic_tensor_spec is not None
            else "deterministic_dimension_squared_greedy_all_mpi_ranks"
        ),
        "raw_tensor_owner_cost_loads": owner_loads,
        "raw_tensor_policy_signatures_identical": True,
        "raw_tensor_persistent_cache": {
            "schema_version": (
                "task035b.raw-tensor-persistent-cache.v2"
            ),
            "enabled": persistent_enabled,
            "mode": persistent_cache_mode,
            "source_commit_sha": source_sha,
            "directory": (
                None
                if cache_directory is None
                else str(cache_directory)
            ),
            "hit_count": cache_hit_count,
            "miss_count": evaluation_count,
            "miss_reasons": cache_miss_reasons,
            "write_count": cache_write_count,
            "read_seconds_max": float(
                comm.allreduce(
                    local_cache_read_seconds,
                    op=MPI.MAX,
                )
            ),
            "write_seconds_max": float(
                comm.allreduce(
                    local_cache_write_seconds,
                    op=MPI.MAX,
                )
            ),
            "read_bytes_sum": int(
                comm.allreduce(
                    local_cache_read_bytes,
                    op=MPI.SUM,
                )
            ),
            "write_bytes_sum": int(
                comm.allreduce(
                    local_cache_write_bytes,
                    op=MPI.SUM,
                )
            ),
            "operator_identity_bound": True,
            "form_signature_bound": bool(
                affine_isotropic_tensor_spec is None
            ),
            "material_and_degree_invalidation_via_ufcx_signature": bool(
                affine_isotropic_tensor_spec is None
            ),
            (
                "material_and_degree_invalidation_via_analytic_spec_"
                "and_element_identity"
            ): bool(affine_isotropic_tensor_spec is not None),
            "geometry_class_invalidation_via_coordinate_sha256": True,
            "manifest_published_after_payload": True,
            "content_checksum_verified": True,
            "pickle_used": False,
            "ordinary_default_changed": False,
        },
        "raw_tensor_owner_evaluation_sync_seconds_max": float(
            comm.allreduce(owner_sync_seconds, op=MPI.MAX)
        ),
        "raw_tensor_backend": (
            "affine_isotropic_reference_gram_v1"
            if affine_isotropic_tensor_spec is not None
            else "compiled_ffcx_cell_kernel"
        ),
        "affine_reference_gram_seconds_max": float(
            comm.allreduce(
                local_reference_gram_seconds,
                op=MPI.MAX,
            )
        ),
        "affine_class_combination_seconds_max": float(
            comm.allreduce(
                local_analytic_combination_seconds,
                op=MPI.MAX,
            )
        ),
        "affine_reference_gram_audits": comm.bcast(
            analytic_factory_audits if comm.rank == 0 else None,
            root=0,
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
        "raw_tensor_logical_broadcast_bytes": logical_broadcast_bytes,
        "raw_tensor_broadcast_seconds_max": float(
            comm.allreduce(local_broadcast_seconds, op=MPI.MAX)
        ),
    }, local_kernel_seconds


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


def _orient_embedding(
    high_element,
    low_element,
    embedding: np.ndarray,
    cell_info: int,
) -> np.ndarray:
    """Map a reference embedding into DOLFINx-oriented coefficients.

    Basix applies the sparse entity transforms in-place.  Using these runtime
    kernels avoids constructing and solving with dense 642-by-642 orientation
    matrices on every class.
    """

    oriented = np.ascontiguousarray(embedding.copy())
    low_element.Tt_apply_right(
        oriented.ravel(),
        high_element.dim,
        int(cell_info),
    )
    high_element.Tt_inv_apply(
        oriented.ravel(),
        low_element.dim,
        int(cell_info),
    )
    return oriented


def build_unconstrained_assembly_time_condensation(
    compiled_form,
    function_space,
    cell_tags,
    *,
    mpc=None,
    appended_global_rows: int = 0,
    appended_support_owned_cell_groups: tuple[np.ndarray, ...] = (),
    appended_support_group_by_row: tuple[int, ...] = (),
    defer_final_assembly: bool = False,
    geometry_tolerance: float = 1.0e-11,
    regionwise_element=None,
    regionwise_low_compiled_form=None,
    regionwise_high_canonical_cell_ids: tuple[int, ...] = (),
    regionwise_mesh_geometry_sha256: str | None = None,
    persistent_cache_directory: Path | None = None,
    persistent_cache_source_sha: str | None = None,
    persistent_cache_mode: str = "off",
    bulk_cell_block_insertion: bool = False,
    affine_isotropic_tensor_spec=None,
) -> AssemblyTimeCondensedSystem:
    """Assemble only the independent H(curl) trace Schur matrix.

    When ``mpc`` is supplied, its trace constraints are applied to each local
    Schur tensor before insertion.  No full-trace matrix or embedded slave
    identity rows are allocated.
    """

    if compiled_form is None:
        if affine_isotropic_tensor_spec is None:
            raise ValueError(
                "assembly-time condensation requires a compiled form "
                "unless the affine/isotropic tensor backend is explicit"
            )
    elif np.dtype(compiled_form.dtype) != np.dtype(np.complex128):
        raise TypeError("assembly-time condensation requires complex128")
    if int(appended_global_rows) < 0:
        raise ValueError("appended_global_rows must be non-negative")
    appended_global_rows = int(appended_global_rows)
    mesh = function_space.mesh
    comm = mesh.comm
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
    kernels = (
        {
            int(tag): None
            for tag in (
                affine_isotropic_tensor_spec.mass_coefficient_by_tag
            )
        }
        if compiled_form is None
        else _cell_integral_kernels(compiled_form)
    )
    unknown_tags = (
        []
        if -1 in kernels
        else sorted(set(map(int, tags)) - set(kernels))
    )
    if unknown_tags:
        raise ValueError(
            f"compiled form has no cell integral for tags {unknown_tags}"
        )

    element = function_space.element
    basix_element = element.basix_element
    dimension = int(element.space_dimension)
    entity_dofs = basix_element.entity_dofs
    interior_positions = np.asarray(entity_dofs[tdim][0], dtype=np.int32)
    if len(interior_positions) == 0:
        raise ValueError("selected H(curl) element has no cell-interior DoFs")
    trace_positions = np.setdiff1d(
        np.arange(dimension, dtype=np.int32),
        interior_positions,
        assume_unique=True,
    )
    regionwise_p = regionwise_element is not None
    local_high_interior = np.ones(owned_cells, dtype=bool)
    regionwise_geometry_hash = None
    low_element = None
    low_orientation_element = None
    low_to_reduced = None
    low_interior_positions = None
    low_trace_positions = None
    high_canonical_ids = tuple(
        sorted({int(value) for value in regionwise_high_canonical_cell_ids})
    )
    low_kernels = None
    if regionwise_p:
        from ..geometry.tetra_mesh_audit import (
            canonical_owned_cell_ids,
            geometry_key_sha256,
        )

        if regionwise_element.element.hash() != basix_element.hash():
            raise ValueError(
                "regionwise-p element differs from the function-space element"
            )
        low_element = regionwise_element.low_element
        if regionwise_low_compiled_form is None:
            raise ValueError(
                "regionwise-p requires a separately compiled low-order "
                "cell form; projecting every low cell from the high kernel "
                "is deliberately disabled"
            )
        if np.dtype(regionwise_low_compiled_form.dtype) != np.dtype(
            np.complex128
        ):
            raise TypeError("regionwise-p low cell form requires complex128")
        low_kernels = _cell_integral_kernels(
            regionwise_low_compiled_form
        )
        low_orientation_element = (
            regionwise_low_compiled_form.function_spaces[0].element
        )
        low_unknown_tags = (
            []
            if -1 in low_kernels
            else sorted(set(map(int, tags)) - set(low_kernels))
        )
        if low_unknown_tags:
            raise ValueError(
                "compiled low-order form has no cell integral for tags "
                f"{low_unknown_tags}"
            )
        low_to_reduced = np.asarray(
            regionwise_element.low_to_reduced,
            dtype=np.float64,
        )
        if low_to_reduced.shape != (
            dimension,
            int(low_element.dim),
        ):
            raise ValueError("regionwise-p embedding has the wrong shape")
        low_interior_positions = np.asarray(
            low_element.entity_dofs[tdim][0],
            dtype=np.int32,
        )
        low_trace_positions = np.setdiff1d(
            np.arange(low_element.dim, dtype=np.int32),
            low_interior_positions,
            assume_unique=True,
        )
        if len(low_trace_positions) != len(trace_positions):
            raise ValueError(
                "regionwise-p low and high trace dimensions disagree"
            )
        canonical_ids, _records, ordered_keys = canonical_owned_cell_ids(mesh)
        regionwise_geometry_hash = geometry_key_sha256(ordered_keys)
        if (
            regionwise_mesh_geometry_sha256 is not None
            and regionwise_geometry_hash
            != str(regionwise_mesh_geometry_sha256)
        ):
            raise ValueError(
                "regionwise-p classifier mesh geometry hash differs from "
                "the actual solve mesh"
            )
        invalid_ids = set(high_canonical_ids) - set(
            range(len(ordered_keys))
        )
        if invalid_ids:
            raise ValueError(
                "regionwise-p high-cell IDs are outside the actual mesh: "
                f"{sorted(invalid_ids)[:8]}"
            )
        local_high_interior = np.isin(
            canonical_ids,
            np.asarray(high_canonical_ids, dtype=np.int64),
        )

    local_cell_dofs: list[np.ndarray] = []
    local_interiors: list[np.ndarray] = []
    for cell in range(owned_cells):
        local = np.asarray(dofmap.cell_dofs(cell), dtype=np.int32)
        original = np.asarray(
            dofmap.index_map.local_to_global(local),
            dtype=PETSc.IntType,
        )
        local_cell_dofs.append(original)
        local_interiors.append(original[interior_positions])
    owned_trace, mapping, trace_rows, full_rows = _owned_trace_numbering(
        function_space,
        tuple(local_interiors),
    )
    trace_constraints = _trace_constraint_map(
        function_space,
        owned_trace,
        mapping,
        trace_rows,
        mpc,
    )
    active_rows = trace_constraints.active_rows
    owned_active = trace_constraints.owned_active_original_dofs
    active_counts = tuple(comm.allgather(len(owned_active)))
    active_start = int(sum(active_counts[: comm.rank]))
    local_appended = appended_global_rows if comm.rank == comm.size - 1 else 0
    matrix_rows = active_rows + appended_global_rows
    cell_trace_data: list[
        tuple[np.ndarray, sparse.csr_matrix, bool]
    ] = []
    for original_dofs in local_cell_dofs:
        cell_trace_data.append(
            _cell_trace_expansion(
                original_dofs[trace_positions],
                trace_constraints,
            )
        )
    preallocation_started = perf_counter()
    diagonal_nnz, off_diagonal_nnz, preallocation_audit = (
        _distributed_trace_preallocation(
            comm,
            tuple(data[0] for data in cell_trace_data),
            active_counts=active_counts,
            appended_global_rows=appended_global_rows,
            appended_support_owned_cell_groups=(
                appended_support_owned_cell_groups
            ),
            appended_support_group_by_row=(
                appended_support_group_by_row
            ),
        )
    )
    preallocation_audit["build_seconds"] = float(
        comm.allreduce(
            perf_counter() - preallocation_started,
            op=MPI.MAX,
        )
    )
    condensed = PETSc.Mat().createAIJ(
        size=(
            (len(owned_active) + local_appended, matrix_rows),
            (len(owned_active) + local_appended, matrix_rows),
        ),
        nnz=(
            diagonal_nnz
            if comm.size == 1
            else (diagonal_nnz, off_diagonal_nnz)
        ),
        comm=comm,
    )
    if condensed.getOwnershipRange()[0] != active_start:
        condensed.destroy()
        raise RuntimeError(
            "PETSc active-trace ownership disagrees with trace numbering"
        )
    condensed.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)

    mesh.topology.create_entity_permutations()
    cell_permutations = mesh.topology.get_cell_permutation_info()
    local_class_coordinates: dict[tuple[Any, ...], np.ndarray] = {}
    cell_raw_metadata: list[
        tuple[tuple[Any, ...], str, tuple[Any, ...]]
    ] = []
    local_metadata_error = None
    try:
        for cell in range(owned_cells):
            canonical_coordinates, widths = (
                _canonical_axis_aligned_coordinates(
                    mesh,
                    cell,
                    tolerance=geometry_tolerance,
                )
            )
            tag = int(tags[cell])
            raw_key = (tag, *widths)
            interior_policy = (
                "high"
                if bool(local_high_interior[cell])
                else "low"
            )
            policy_raw_key = (interior_policy, *raw_key)
            previous = local_class_coordinates.get(policy_raw_key)
            if previous is not None and not np.array_equal(
                previous,
                canonical_coordinates,
            ):
                raise RuntimeError(
                    "raw tensor class has inconsistent canonical geometry "
                    "on one MPI rank"
                )
            local_class_coordinates.setdefault(
                policy_raw_key,
                canonical_coordinates,
            )
            cell_raw_metadata.append(
                (raw_key, interior_policy, policy_raw_key)
            )
    except Exception as error:
        local_metadata_error = f"{type(error).__name__}: {error}"
    metadata_errors = comm.allgather(local_metadata_error)
    if any(error is not None for error in metadata_errors):
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
    policy_forms: dict[
        str,
        tuple[Any | None, dict[int, Any], int, Any],
    ] = {
        "high": (
            compiled_form,
            kernels,
            dimension,
            basix_element,
        ),
    }
    if regionwise_p:
        assert regionwise_low_compiled_form is not None
        assert low_kernels is not None
        assert low_element is not None
        policy_forms["low"] = (
            regionwise_low_compiled_form,
            low_kernels,
            int(low_element.dim),
            low_element,
        )
    try:
        raw_cache, raw_cache_audit, local_kernel_seconds = (
            _global_raw_tensor_cache(
                comm,
                local_class_coordinates,
                policy_forms,
                persistent_cache_directory=persistent_cache_directory,
                persistent_cache_source_sha=persistent_cache_source_sha,
                persistent_cache_mode=persistent_cache_mode,
                affine_isotropic_tensor_spec=(
                    affine_isotropic_tensor_spec
                ),
            )
        )
    except Exception:
        condensed.destroy()
        raise
    schur_cache: dict[tuple[Any, ...], np.ndarray] = {}
    recovery_cache: dict[tuple[Any, ...], np.ndarray] = {}
    lu_cache: dict[tuple[Any, ...], tuple[np.ndarray, np.ndarray]] = {}
    rhs_projection_cache: dict[tuple[Any, ...], np.ndarray] = {}
    solution_embedding_cache: dict[tuple[Any, ...], np.ndarray] = {}
    dual_recovery_cache: dict[tuple[Any, ...], np.ndarray] = {}
    rhs_trace_cache: dict[tuple[Any, ...], np.ndarray] = {}
    residual_projection_cache: dict[tuple[Any, ...], np.ndarray] = {}
    recovery_maps: list[CellRecoveryMap] = []
    local_schur_seconds = 0.0
    local_orientation_seconds = 0.0
    local_aii_factor_seconds = 0.0
    local_aii_solve_seconds = 0.0
    local_schur_product_seconds = 0.0
    local_constraint_seconds = 0.0
    local_insert_seconds = 0.0
    bulk_inserter = (
        _DenseBlockBatchInserter(condensed)
        if bulk_cell_block_insertion
        else None
    )
    conventional_insert_call_count = 0
    conventional_scalar_entry_count = 0
    for cell, (original_dofs, metadata) in enumerate(
        zip(local_cell_dofs, cell_raw_metadata, strict=True)
    ):
        raw_key, interior_policy, policy_raw_key = metadata
        tensor = raw_cache[policy_raw_key]
        class_key = (
            *raw_key,
            int(cell_permutations[cell]),
            interior_policy,
        )
        schur = schur_cache.get(class_key)
        if schur is None:
            schur_started = perf_counter()
            orientation_started = perf_counter()
            oriented = tensor.copy()
            if interior_policy == "low":
                assert low_element is not None
                assert low_orientation_element is not None
                assert low_to_reduced is not None
                assert low_interior_positions is not None
                assert low_trace_positions is not None
                oriented_embedding = _orient_embedding(
                    basix_element,
                    low_element,
                    low_to_reduced,
                    int(cell_permutations[cell]),
                )
                _orient_cell_tensor(
                    low_orientation_element,
                    oriented,
                    np.asarray(
                        cell_permutations[cell : cell + 1],
                        dtype=np.uint32,
                    ),
                )
                trace_identity_error = float(
                    np.max(
                        np.abs(
                            oriented_embedding[
                                np.ix_(
                                    trace_positions,
                                    low_trace_positions,
                                )
                            ]
                            - np.eye(len(trace_positions))
                        ),
                        initial=0.0,
                    )
                )
                trace_interior_leakage = float(
                    np.max(
                        np.abs(
                            oriented_embedding[
                                np.ix_(
                                    trace_positions,
                                    low_interior_positions,
                                )
                            ]
                        ),
                        initial=0.0,
                    )
                )
                if (
                    trace_identity_error > 2.0e-11
                    or trace_interior_leakage > 2.0e-11
                ):
                    raise RuntimeError(
                        "regionwise-p orientation does not preserve the "
                        "shared low-order trace"
                    )
                active_tensor = oriented
                active_interior_positions = low_interior_positions
                active_trace_positions = low_trace_positions
                interior_embedding_from_trace = oriented_embedding[
                    np.ix_(interior_positions, low_trace_positions)
                ]
                interior_embedding_from_interior = oriented_embedding[
                    np.ix_(interior_positions, low_interior_positions)
                ]
            else:
                _orient_cell_tensor(
                    element,
                    oriented,
                    np.asarray(
                        cell_permutations[cell : cell + 1],
                        dtype=np.uint32,
                    ),
                )
                active_tensor = oriented
                active_interior_positions = interior_positions
                active_trace_positions = trace_positions
                interior_embedding_from_trace = np.zeros(
                    (len(interior_positions), len(trace_positions)),
                    dtype=np.float64,
                )
                interior_embedding_from_interior = np.eye(
                    len(interior_positions),
                    dtype=np.float64,
                )
            local_orientation_seconds += (
                perf_counter() - orientation_started
            )
            A_ii = active_tensor[
                np.ix_(
                    active_interior_positions,
                    active_interior_positions,
                )
            ]
            A_it = active_tensor[
                np.ix_(
                    active_interior_positions,
                    active_trace_positions,
                )
            ]
            A_ti = active_tensor[
                np.ix_(
                    active_trace_positions,
                    active_interior_positions,
                )
            ]
            A_tt = active_tensor[
                np.ix_(active_trace_positions, active_trace_positions)
            ]
            factor_started = perf_counter()
            active_interior_lu = lu_factor(A_ii)
            local_aii_factor_seconds += (
                perf_counter() - factor_started
            )
            solve_started = perf_counter()
            active_interior_from_trace = -lu_solve(
                active_interior_lu,
                A_it,
            )
            interior_from_trace = (
                interior_embedding_from_trace
                + interior_embedding_from_interior
                @ active_interior_from_trace
            )
            adjoint_trace_solution = lu_solve(
                active_interior_lu,
                A_ti.conj().T,
                trans=2,
            )
            dual_interior_from_trace = (
                interior_embedding_from_trace
                - interior_embedding_from_interior
                @ adjoint_trace_solution
            )
            local_aii_solve_seconds += perf_counter() - solve_started
            trace_from_interior_rhs = (
                dual_interior_from_trace.conj().T
            )
            schur_product_started = perf_counter()
            schur = A_tt + A_ti @ active_interior_from_trace
            local_schur_product_seconds += (
                perf_counter() - schur_product_started
            )
            local_schur_seconds += perf_counter() - schur_started
            schur_cache[class_key] = schur
            recovery_cache[class_key] = interior_from_trace
            lu_cache[class_key] = active_interior_lu
            rhs_projection_cache[class_key] = (
                interior_embedding_from_interior.conj().T
            )
            solution_embedding_cache[class_key] = (
                interior_embedding_from_interior
            )
            dual_recovery_cache[class_key] = dual_interior_from_trace
            rhs_trace_cache[class_key] = trace_from_interior_rhs
            residual_projection_cache[class_key] = (
                interior_embedding_from_interior.conj().T
            )
        trace_original = original_dofs[trace_positions]
        active_ids, local_expansion, identity_expansion = cell_trace_data[cell]
        constraint_started = perf_counter()
        active_schur = _constrain_local_schur(
            schur,
            local_expansion,
            identity_expansion,
        )
        local_constraint_seconds += perf_counter() - constraint_started
        insert_started = perf_counter()
        active_schur_values = np.asarray(
            active_schur,
            dtype=PETSc.ScalarType,
        )
        if bulk_inserter is None:
            condensed.setValues(
                active_ids,
                active_ids,
                active_schur_values,
                addv=PETSc.InsertMode.ADD_VALUES,
            )
            conventional_insert_call_count += 1
            conventional_scalar_entry_count += int(
                active_schur_values.size
            )
        else:
            bulk_inserter.add(active_ids, active_schur_values)
        local_insert_seconds += perf_counter() - insert_started
        recovery_maps.append(
            CellRecoveryMap(
                interior_original_dofs=original_dofs[interior_positions].copy(),
                trace_original_dofs=trace_original.copy(),
                cell_local_dofs=np.asarray(
                    dofmap.cell_dofs(cell),
                    dtype=np.int32,
                ).copy(),
                raw_key=tuple(raw_key),
                cell_permutation=int(cell_permutations[cell]),
                interior_policy=interior_policy,
                class_key=class_key,
            )
        )
    if bulk_inserter is None:
        bulk_insertion_audit = {
            "schema_version": (
                "task035b.dense-cell-block-bulk-insertion.v1"
            ),
            "enabled": False,
            "backend": "petsc4py.Mat.setValues",
            "add_values_semantics": True,
            "maximum_payload_bytes": None,
            "cell_block_count_global": int(
                comm.allreduce(
                    conventional_insert_call_count,
                    op=MPI.SUM,
                )
            ),
            "scalar_entry_count_global": int(
                comm.allreduce(
                    conventional_scalar_entry_count,
                    op=MPI.SUM,
                )
            ),
            "ijv_call_count_sum": 0,
            "ijv_call_count_max_per_rank": 0,
            "peak_temporary_payload_bytes_max_per_rank": 0,
            "per_cell_petsc_mat_set_values_call_eliminated": False,
            "ordinary_default_changed": False,
        }
    else:
        insert_started = perf_counter()
        bulk_inserter.flush()
        local_insert_seconds += perf_counter() - insert_started
        bulk_insertion_audit = bulk_inserter.audit(comm)
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
        condensed.assemble()
        final_assembly_seconds = float(
            comm.allreduce(
                perf_counter() - assembly_started,
                op=MPI.MAX,
            )
        )
    interior_rows = full_rows - trace_rows
    global_cells = int(comm.allreduce(owned_cells, op=MPI.SUM))
    local_high_cells = int(np.count_nonzero(local_high_interior))
    global_high_cells = int(
        comm.allreduce(local_high_cells, op=MPI.SUM)
    )
    global_low_cells = global_cells - global_high_cells
    low_interior_dimension = (
        len(interior_positions)
        if low_interior_positions is None
        else len(low_interior_positions)
    )
    active_interior_rows = (
        global_high_cells * len(interior_positions)
        + global_low_cells * low_interior_dimension
    )
    raw_kernel_evaluation_count = int(
        raw_cache_audit["raw_tensor_kernel_evaluation_count"]
    )
    oriented_class_count = int(comm.allreduce(len(schur_cache), op=MPI.SUM))
    native_object_ledger = _python_visible_native_array_ledger(
        comm,
        {
            "raw_tensor_cache": tuple(raw_cache.values()),
            "schur_cache": tuple(schur_cache.values()),
            "interior_recovery_cache": tuple(
                recovery_cache.values()
            ),
            "interior_lu_cache": tuple(lu_cache.values()),
            "rhs_projection_cache": tuple(
                rhs_projection_cache.values()
            ),
            "solution_embedding_cache": tuple(
                solution_embedding_cache.values()
            ),
            "dual_recovery_cache": tuple(
                dual_recovery_cache.values()
            ),
            "trace_from_interior_rhs_cache": tuple(
                rhs_trace_cache.values()
            ),
            "residual_projection_cache": tuple(
                residual_projection_cache.values()
            ),
            "cell_recovery_numbering": tuple(
                (
                    recovery.interior_original_dofs,
                    recovery.trace_original_dofs,
                    recovery.cell_local_dofs,
                )
                for recovery in recovery_maps
            ),
            "trace_constraint_numbering": (
                trace_constraints.owned_active_original_dofs,
                tuple(
                    trace_constraints.expansion_by_original.values()
                ),
            ),
        },
        transient_categories=("raw_tensor_cache",),
    )
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
        dual_interior_from_trace_by_class=dual_recovery_cache,
        appended_dual_interior_by_cell=tuple(
            {} for _cell in recovery_maps
        ),
        appended_dual_rows_registered=set(),
        trace_from_interior_rhs_by_class=rhs_trace_cache,
        interior_residual_projection_by_class=residual_projection_cache,
        full_rows=full_rows,
        trace_rows=trace_rows,
        active_rows=active_rows,
        appended_rows=appended_global_rows,
        interior_rows=interior_rows,
        active_interior_rows=active_interior_rows,
        build_audit={
            "schema_version": "task035b.assembly-time-cell-condensation.v1",
            "status": "unconstrained_trace_schur_built_without_full_matrix",
            "full_rows": full_rows,
            "trace_rows": trace_rows,
            "active_rows": active_rows,
            "appended_rows": appended_global_rows,
            "matrix_rows": matrix_rows,
            "interior_rows": interior_rows,
            "owned_cell_count_global": global_cells,
            "local_tensor_dimension": dimension,
            "local_trace_dimension": int(len(trace_positions)),
            "local_interior_dimension": int(len(interior_positions)),
            "regionwise_interior_p_active": regionwise_p,
            "regionwise_high_cell_count": global_high_cells,
            "regionwise_low_cell_count": global_low_cells,
            "regionwise_high_interior_dimension": int(
                len(interior_positions)
            ),
            "regionwise_low_interior_dimension": int(
                low_interior_dimension
            ),
            "regionwise_trace_degree": (
                None
                if regionwise_element is None
                else int(regionwise_element.trace_degree)
            ),
            "regionwise_low_interior_degree": (
                None
                if regionwise_element is None
                else int(regionwise_element.low_interior_degree)
            ),
            "regionwise_high_interior_degree": (
                None
                if regionwise_element is None
                else int(regionwise_element.interior_degree)
            ),
            "active_cell_interior_modes": int(active_interior_rows),
            "active_full3d_equivalent_dofs": int(
                trace_rows + active_interior_rows
            ),
            "storage_function_space_dofs": int(full_rows),
            "inactive_max_p_rows_retained_in_matrix": False,
            "regionwise_mesh_geometry_sha256": regionwise_geometry_hash,
            "regionwise_high_canonical_cell_ids": list(
                high_canonical_ids
            ),
            "regionwise_low_cell_kernel_compiled_directly": bool(
                regionwise_p
            ),
            "full_global_matrix_allocated": False,
            "full_trace_matrix_allocated": False,
            "embedded_mpc_slave_identity_rows_allocated": False,
            "assembly_cost_avoided": True,
            "final_matrix_assembly_deferred_for_appended_rows": bool(
                defer_final_assembly
            ),
            "axis_aligned_affine_geometry_verified": True,
            **raw_cache_audit,
            "oriented_schur_class_count_sum": oriented_class_count,
            "cell_kernel_evaluation_fraction": float(
                raw_kernel_evaluation_count / max(global_cells, 1)
            ),
            "kernel_seconds_max": float(
                comm.allreduce(local_kernel_seconds, op=MPI.MAX)
            ),
            "local_schur_seconds_max": float(
                comm.allreduce(local_schur_seconds, op=MPI.MAX)
            ),
            "orientation_seconds_max": float(
                comm.allreduce(
                    local_orientation_seconds,
                    op=MPI.MAX,
                )
            ),
            "aii_factor_seconds_max": float(
                comm.allreduce(
                    local_aii_factor_seconds,
                    op=MPI.MAX,
                )
            ),
            "aii_solve_seconds_max": float(
                comm.allreduce(
                    local_aii_solve_seconds,
                    op=MPI.MAX,
                )
            ),
            "schur_product_seconds_max": float(
                comm.allreduce(
                    local_schur_product_seconds,
                    op=MPI.MAX,
                )
            ),
            "constraint_projection_seconds_max": float(
                comm.allreduce(
                    local_constraint_seconds,
                    op=MPI.MAX,
                )
            ),
            "local_insert_seconds_max": float(
                comm.allreduce(local_insert_seconds, op=MPI.MAX)
            ),
            "bulk_cell_block_insertion": bulk_insertion_audit,
            "pre_final_assembly_sync_seconds_max": (
                preassembly_sync_seconds
            ),
            "final_assembly_seconds": final_assembly_seconds,
            "trace_preallocation_seconds": float(
                preallocation_audit["build_seconds"]
            ),
            "trace_preallocation": preallocation_audit,
            "trace_constraints": trace_constraints.build_audit,
            "native_object_ledger": native_object_ledger,
            "total_build_seconds": float(
                comm.allreduce(perf_counter() - started, op=MPI.MAX)
            ),
        },
        affine_isotropic_tensor_spec=affine_isotropic_tensor_spec,
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
        float(relative_tolerance)
        * float(np.max(np.abs(owned_values), initial=0.0)),
    )
    active = condensed.matrix.createVecRight()
    owned_trace = condensed.owned_trace_original_dofs
    if len(owned_trace):
        trace_values = owned_values[
            np.asarray(owned_trace, dtype=np.int64) - row_start
        ]
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
            int(interior_rows.min()) < row_start
            or int(interior_rows.max()) >= row_end
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
                condensed.interior_from_trace_by_class[
                    cell.class_key
                ].conj().T
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
        if len(rows) and (
            int(rows.min()) < left_start or int(rows.max()) >= left_end
        ):
            raise ValueError(
                "owned cell-interior bilinear rows are outside local ownership"
            )
        local_rows = rows - left_start
        left_values = left[local_rows]
        right_values = right[local_rows]
        if (
            not np.any(left_values)
            or not np.any(right_values)
        ):
            continue
        projection = condensed.interior_rhs_projection_by_class[
            cell.class_key
        ]
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
        condensed.matrix.getComm().tompi4py().allreduce(
            local,
            op=MPI.SUM,
        )
    )


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
                condensed.trace_constraints.expansion_by_original[
                    int(original)
                ]
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
                    "owned cell-interior recovery RHS rows are outside "
                    "local ownership"
                )
            values = (
                values
                + condensed.interior_solution_embedding_by_class[
                    cell.class_key
                ]
                @ lu_solve(
                    condensed.interior_lu_by_class[cell.class_key],
                    condensed.interior_rhs_projection_by_class[
                        cell.class_key
                    ]
                    @ rhs_values[rows - rhs_start],
                )
            )
        result.append((cell.interior_original_dofs, values))
    return tuple(result)


def _global_reduced_dual_values(
    condensed: AssemblyTimeCondensedSystem,
    reduced_adjoint: PETSc.Vec | np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return active-trace and appended adjoint values on every rank."""

    reduced_rows = int(condensed.active_rows + condensed.appended_rows)
    if isinstance(reduced_adjoint, np.ndarray):
        values = np.asarray(reduced_adjoint, dtype=np.complex128)
        if values.shape != (reduced_rows,):
            raise ValueError(
                "reduced adjoint array must contain the active trace and "
                "every appended row"
            )
        return (
            values[: condensed.active_rows].copy(),
            values[condensed.active_rows :].copy(),
        )

    if int(reduced_adjoint.getSize()) != reduced_rows:
        raise ValueError(
            "reduced adjoint must contain the active trace followed by "
            "every appended row"
        )
    comm = condensed.matrix.getComm().tompi4py()
    row_start, row_end = map(
        int,
        reduced_adjoint.getOwnershipRange(),
    )
    local_ids = np.arange(row_start, row_end, dtype=np.int64)
    local_values = np.asarray(
        reduced_adjoint.getArray(readonly=True),
        dtype=np.complex128,
    )
    packets = comm.allgather((local_ids, local_values))
    global_values = np.empty(reduced_rows, dtype=np.complex128)
    seen = np.zeros(reduced_rows, dtype=bool)
    for ids, packet_values in packets:
        if len(ids):
            global_values[ids] = packet_values
            seen[ids] = True
    if not np.all(seen):
        raise RuntimeError(
            "distributed reduced adjoint does not close globally"
        )
    return (
        global_values[: condensed.active_rows],
        global_values[condensed.active_rows :],
    )


def register_appended_dual_interior_coupling(
    condensed: AssemblyTimeCondensedSystem,
    appended_row: int,
    full_left_vectors: tuple[PETSc.Vec, ...],
    coefficients: tuple[complex, ...],
    *,
    row_scale: complex,
) -> None:
    """Cache one exact auxiliary-row contribution to eliminated duals.

    If the full augmented row is
    ``C = row_scale * (sum_j coefficients[j] * l_j)^H``, this stores the
    nonzero owned-cell columns

    ``-E_ii A_ii^{-H} C_i^H``.

    The cache is deliberately populated by the caller only for an explicit
    adjoint-recovery retain opt-in.  No full FE or trace matrix is allocated.
    """

    appended_row = int(appended_row)
    if not 0 <= appended_row < condensed.appended_rows:
        raise ValueError("appended dual row is outside the reduced system")
    if appended_row in condensed.appended_dual_rows_registered:
        raise ValueError("appended dual row was already registered")
    if (
        not full_left_vectors
        or len(full_left_vectors) != len(coefficients)
    ):
        raise ValueError(
            "full left vectors and coefficients must be nonempty and aligned"
        )
    ownership = None
    local_arrays: list[np.ndarray] = []
    for vector in full_left_vectors:
        if int(vector.getSize()) != int(condensed.full_rows):
            raise ValueError(
                "appended left vector differs from the full FE space"
            )
        vector_ownership = tuple(map(int, vector.getOwnershipRange()))
        if ownership is None:
            ownership = vector_ownership
        elif vector_ownership != ownership:
            raise ValueError(
                "appended left vectors have different ownership ranges"
            )
        local_arrays.append(
            np.asarray(
                vector.getArray(readonly=True),
                dtype=np.complex128,
            )
        )
    assert ownership is not None
    row_start, row_end = ownership
    conjugate_scale = np.conj(complex(row_scale))
    for cell_index, cell in enumerate(condensed.cell_recovery_maps):
        rows = np.asarray(cell.interior_original_dofs, dtype=np.int64)
        if len(rows) and (
            int(rows.min()) < row_start or int(rows.max()) >= row_end
        ):
            raise ValueError(
                "owned cell-interior appended coupling rows are outside "
                "local ownership"
            )
        local_rows = rows - row_start
        combined = np.zeros(len(rows), dtype=np.complex128)
        for coefficient, values in zip(
            coefficients,
            local_arrays,
            strict=True,
        ):
            combined += complex(coefficient) * values[local_rows]
        if not np.any(combined):
            continue
        projected = (
            condensed.interior_rhs_projection_by_class[cell.class_key]
            @ combined
        )
        recovered = (
            -conjugate_scale
            * (
                condensed.interior_solution_embedding_by_class[
                    cell.class_key
                ]
                @ lu_solve(
                    condensed.interior_lu_by_class[cell.class_key],
                    projected,
                    trans=2,
                )
            )
        )
        if np.any(recovered):
            condensed.appended_dual_interior_by_cell[cell_index][
                appended_row
            ] = np.asarray(recovered, dtype=np.complex128)
    condensed.appended_dual_rows_registered.add(appended_row)


def _assert_appended_dual_recovery_complete(
    condensed: AssemblyTimeCondensedSystem,
) -> None:
    expected = tuple(range(condensed.appended_rows))
    local = tuple(sorted(condensed.appended_dual_rows_registered))
    packets = (
        condensed.matrix.getComm().tompi4py().allgather(local)
    )
    if any(packet != expected for packet in packets):
        raise RuntimeError(
            "exact augmented dual recovery is unavailable because appended "
            "interior coupling rows are incomplete"
        )


def recover_full_dual_from_active_trace(
    condensed: AssemblyTimeCondensedSystem,
    reduced_adjoint: PETSc.Vec | np.ndarray,
) -> PETSc.Vec:
    """Recover the full oriented complex-Hermitian dual without a full matrix.

    The physically active trace is expanded with the exact Floquet constraint
    map ``z_t_full = C_t z_t``.  On every owned cell, the eliminated dual is

    ``z_i = -A_ii^{-H}(A_ti^H z_t_full + C_i^H z_aux)``.

    Regionwise reduced-interior embeddings and DOLFINx/Basix cell orientation
    transforms are already incorporated in the cached class recovery matrix.
    The returned PETSc vector uses the original unconstrained global FE
    numbering and contains owned trace and cell-interior values only; it does
    not allocate or assemble a full global operator.
    """

    _assert_appended_dual_recovery_complete(condensed)
    active, appended = _global_reduced_dual_values(
        condensed,
        reduced_adjoint,
    )
    comm = condensed.matrix.getComm().tompi4py()
    local_interior = [
        np.asarray(cell.interior_original_dofs, dtype=np.int64)
        for cell in condensed.cell_recovery_maps
    ]
    local_original = np.concatenate(
        (
            np.asarray(
                condensed.owned_trace_original_dofs,
                dtype=np.int64,
            ),
            *local_interior,
        )
    )
    if len(np.unique(local_original)) != len(local_original):
        raise RuntimeError(
            "owned trace and cell-interior dual rows are not disjoint"
        )
    local_original.sort()
    counts = comm.allgather(int(len(local_original)))
    expected_start = int(sum(counts[: comm.rank]))
    expected_end = expected_start + int(len(local_original))
    if (
        expected_end > expected_start
        and not np.array_equal(
            local_original,
            np.arange(expected_start, expected_end, dtype=np.int64),
        )
    ):
        raise RuntimeError(
            "original FE dual numbering does not match PETSc ownership"
        )
    if int(sum(counts)) != int(condensed.full_rows):
        raise RuntimeError(
            "owned full dual rows do not cover the original FE space"
        )

    full_dual = PETSc.Vec().createMPI(
        (len(local_original), int(condensed.full_rows)),
        comm=condensed.matrix.getComm(),
    )
    full_dual.setName("assembly_time_recovered_full_dual")
    owned_trace = np.asarray(
        condensed.owned_trace_original_dofs,
        dtype=np.int64,
    )
    if len(owned_trace):
        trace_values = np.empty(len(owned_trace), dtype=np.complex128)
        for index, original in enumerate(owned_trace):
            active_ids, coefficients = (
                condensed.trace_constraints.expansion_by_original[
                    int(original)
                ]
            )
            trace_values[index] = np.dot(
                coefficients,
                active[active_ids],
            )
        full_dual.setValues(
            _idx(owned_trace),
            np.asarray(trace_values, dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )

    for cell_index, cell in enumerate(condensed.cell_recovery_maps):
        local_trace = np.empty(
            len(cell.trace_original_dofs),
            dtype=np.complex128,
        )
        for row, original in enumerate(cell.trace_original_dofs):
            active_ids, coefficients = (
                condensed.trace_constraints.expansion_by_original[
                    int(original)
                ]
            )
            local_trace[row] = np.dot(
                coefficients,
                active[active_ids],
            )
        interior_values = (
            condensed.dual_interior_from_trace_by_class[cell.class_key]
            @ local_trace
        )
        for appended_row, column in (
            condensed.appended_dual_interior_by_cell[cell_index].items()
        ):
            interior_values += column * appended[appended_row]
        full_dual.setValues(
            _idx(cell.interior_original_dofs),
            np.asarray(interior_values, dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    full_dual.assemble()
    return full_dual


def assembly_time_dual_recovery_context(
    condensed: AssemblyTimeCondensedSystem,
) -> Mapping[str, Any]:
    """Expose immutable metadata and the matrix-free dual recovery callable."""

    _assert_appended_dual_recovery_complete(condensed)
    comm = condensed.matrix.getComm().tompi4py()
    local_blocks = sum(
        len(block)
        for block in condensed.appended_dual_interior_by_cell
    )
    local_bytes = sum(
        int(column.nbytes)
        for block in condensed.appended_dual_interior_by_cell
        for column in block.values()
    )
    global_blocks = int(comm.allreduce(local_blocks, op=MPI.SUM))
    global_bytes = int(comm.allreduce(local_bytes, op=MPI.SUM))
    return MappingProxyType(
        {
            "schema_version": (
                "task035b.assembly-time-hermitian-dual-recovery.v2"
            ),
            "state_layout": (
                "floquet_independent_active_trace_plus_appended_rows"
            ),
            "active_trace_rows": int(condensed.active_rows),
            "full_trace_rows": int(condensed.trace_rows),
            "full_fe_rows": int(condensed.full_rows),
            "appended_rows": int(condensed.appended_rows),
            "exact_augmented_interior_coupling": True,
            "appended_coupling_rows_registered": int(
                len(condensed.appended_dual_rows_registered)
            ),
            "appended_nonzero_cell_blocks_global": global_blocks,
            "appended_recovery_storage_bytes_global": global_bytes,
            "full_global_matrix_required": False,
            "recover_full_fe_dual": (
                lambda reduced_adjoint: (
                    recover_full_dual_from_active_trace(
                        condensed,
                        reduced_adjoint,
                    )
                )
            ),
        }
    )


def project_mpc_vector_to_active_trace(
    condensed: AssemblyTimeCondensedSystem,
    full_vector: PETSc.Vec,
    *,
    eliminated_tolerance: float = 1.0e-12,
) -> PETSc.Vec:
    """Project an already MPC-assembled full-space vector to active trace rows.

    ``dolfinx_mpc.assemble_vector`` has already applied ``C^H`` and leaves
    slave entries at zero.  This function verifies that no eliminated
    cell-interior or slave entry is nonzero before physically dropping them.
    """

    if full_vector.getSize() != condensed.full_rows:
        raise ValueError("full MPC vector size differs from the FE space")
    comm = condensed.matrix.getComm().tompi4py()
    row_start, row_end = full_vector.getOwnershipRange()
    owned_original = np.arange(row_start, row_end, dtype=PETSc.IntType)
    owned_values = np.asarray(
        full_vector.getArray(readonly=True),
        dtype=np.complex128,
    )
    active_set = set(
        int(value)
        for value in condensed.trace_constraints.owned_active_original_dofs
    )
    eliminated_mask = np.asarray(
        [int(row) not in active_set for row in owned_original],
        dtype=bool,
    )
    local_max_eliminated = float(
        np.max(np.abs(owned_values[eliminated_mask]), initial=0.0)
    )
    max_eliminated = float(
        comm.allreduce(local_max_eliminated, op=MPI.MAX)
    )
    if max_eliminated > eliminated_tolerance:
        raise ValueError(
            "MPC vector has nonzero eliminated interior/slave entries: "
            f"{max_eliminated:.3e}"
        )
    active_vector = condensed.matrix.createVecRight()
    active_original = (
        condensed.trace_constraints.owned_active_original_dofs
    )
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
    "assembly_time_dual_recovery_context",
    "build_unconstrained_assembly_time_condensation",
    "cell_interior_schur_bilinear",
    "condense_unconstrained_vector_to_active_trace",
    "project_mpc_vector_to_active_trace",
    "recover_full_dual_from_active_trace",
    "recover_owned_cell_interiors",
    "register_appended_dual_interior_coupling",
]
