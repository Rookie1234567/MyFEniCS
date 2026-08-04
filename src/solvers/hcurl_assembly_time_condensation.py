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

from dataclasses import dataclass, field
from collections.abc import Mapping
import hashlib
from time import perf_counter
from types import MappingProxyType
from typing import Any

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
    """Physically reduced trace system and matrix-free recovery metadata."""

    matrix: PETSc.Mat | None
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


def _global_raw_tensor_cache(
    comm,
    local_class_coordinates: dict[tuple[Any, ...], np.ndarray],
    policy_forms: dict[
        str,
        tuple[Any, dict[int, Any], int],
    ],
) -> tuple[dict[tuple[Any, ...], np.ndarray], dict[str, Any], float]:
    """Evaluate each raw tensor class once globally, then broadcast it.

    Every rank participates in the deterministic class order.  Only ranks
    owning cells in a class retain its tensor after the broadcast.
    """

    local_policy_signature = {
        policy: {
            "dimension": int(dimension),
            "kernel_ids": tuple(sorted(int(key) for key in kernels)),
            "dtype": str(np.dtype(compiled_form.dtype)),
            "element_hash": int(
                compiled_form.function_spaces[0].element.basix_element.hash()
            ),
            "ufcx_form_signature": compiled_form.module.ffi.string(
                compiled_form.ufcx_form.signature
            ).decode(
                "ascii"
            ),
        }
        for policy, (compiled_form, kernels, dimension) in policy_forms.items()
    }
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
        owner = min(range(comm.size), key=lambda rank: (owner_loads[rank], rank))
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
            locally_evaluated[key] = _tabulate_raw_tensor_class(
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

    evaluation_count = int(
        comm.allreduce(local_evaluations, op=MPI.SUM)
    )
    use_count = int(
        comm.allreduce(len(local_class_coordinates), op=MPI.SUM)
    )
    unique_count = len(global_coordinates)
    if evaluation_count != unique_count:
        raise RuntimeError(
            "global raw tensor evaluation count does not match unique classes"
        )
    if set(cache) != local_keys:
        raise RuntimeError("global raw tensor cache is incomplete on this rank")
    return cache, {
        "raw_tensor_class_count_sum": evaluation_count,
        "raw_tensor_class_use_count_sum": use_count,
        "raw_tensor_class_count_global_unique": unique_count,
        "raw_tensor_global_owner_policy": (
            "deterministic_dimension_squared_greedy_all_mpi_ranks"
        ),
        "raw_tensor_owner_cost_loads": owner_loads,
        "raw_tensor_policy_signatures_identical": True,
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
    retain_local_schur_for_matrix_free: bool = False,
    materialize_global_matrix: bool = True,
    geometry_tolerance: float = 1.0e-11,
) -> AssemblyTimeCondensedSystem:
    """Assemble only the independent H(curl) trace Schur matrix.

    When ``mpc`` is supplied, its trace constraints are applied to each local
    Schur tensor before insertion.  No full-trace matrix or embedded slave
    identity rows are allocated.

    ``retain_local_schur_for_matrix_free`` retains one readonly Schur array
    per local class for a later owner-computes action.
    """

    if np.dtype(compiled_form.dtype) != np.dtype(np.complex128):
        raise TypeError("assembly-time condensation requires complex128")
    if int(appended_global_rows) < 0:
        raise ValueError("appended_global_rows must be non-negative")
    materialize_global_matrix = bool(materialize_global_matrix)
    if not materialize_global_matrix and not retain_local_schur_for_matrix_free:
        raise ValueError(
            "action-only condensation requires retained local Schur classes"
        )
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
    kernels = _cell_integral_kernels(compiled_form)
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
    if materialize_global_matrix:
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
    else:
        condensed = None
        preallocation_audit = {
            "status": "not_run_action_only",
            "build_seconds": None,
        }

    mesh.topology.create_entity_permutations()
    cell_permutations = mesh.topology.get_cell_permutation_info()
    local_class_coordinates: dict[tuple[Any, ...], np.ndarray] = {}
    cell_raw_metadata: list[
        tuple[tuple[Any, ...], tuple[Any, ...]]
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
            policy_raw_key = ("actual_space", *raw_key)
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
                (raw_key, policy_raw_key)
            )
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
    policy_forms: dict[str, tuple[Any, dict[int, Any], int]] = {
        "actual_space": (compiled_form, kernels, dimension),
    }
    try:
        raw_cache, raw_cache_audit, local_kernel_seconds = (
            _global_raw_tensor_cache(
                comm,
                local_class_coordinates,
                policy_forms,
            )
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
    recovery_maps: list[CellRecoveryMap] = []
    local_schur_seconds = 0.0
    local_insert_seconds = 0.0
    for cell, (original_dofs, metadata) in enumerate(
        zip(local_cell_dofs, cell_raw_metadata, strict=True)
    ):
        raw_key, policy_raw_key = metadata
        tensor = raw_cache[policy_raw_key]
        class_key = (
            *raw_key,
            int(cell_permutations[cell]),
        )
        schur = schur_cache.get(class_key)
        if schur is None:
            schur_started = perf_counter()
            oriented = tensor.copy()
            _orient_cell_tensor(
                element,
                oriented,
                np.asarray(
                    cell_permutations[cell : cell + 1],
                    dtype=np.uint32,
                ),
            )
            A_ii = oriented[
                np.ix_(interior_positions, interior_positions)
            ]
            A_it = oriented[
                np.ix_(interior_positions, trace_positions)
            ]
            A_ti = oriented[
                np.ix_(trace_positions, interior_positions)
            ]
            A_tt = oriented[np.ix_(trace_positions, trace_positions)]
            interior_lu = lu_factor(A_ii)
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
            schur = A_tt + A_ti @ interior_from_trace
            local_schur_seconds += perf_counter() - schur_started
            schur_cache[class_key] = schur
            recovery_cache[class_key] = interior_from_trace
            lu_cache[class_key] = interior_lu
            interior_identity = np.eye(
                len(interior_positions),
                dtype=np.float64,
            )
            rhs_projection_cache[class_key] = interior_identity
            solution_embedding_cache[class_key] = interior_identity
            rhs_trace_cache[class_key] = trace_from_interior_rhs
            residual_projection_cache[class_key] = interior_identity
        trace_original = original_dofs[trace_positions]
        active_ids, local_expansion, identity_expansion = cell_trace_data[cell]
        if materialize_global_matrix:
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
        recovery_maps.append(
            CellRecoveryMap(
                interior_original_dofs=original_dofs[interior_positions].copy(),
                trace_original_dofs=trace_original.copy(),
                class_key=class_key,
            )
        )
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
    interior_rows = full_rows - trace_rows
    global_cells = int(comm.allreduce(owned_cells, op=MPI.SUM))
    active_interior_rows = interior_rows
    raw_class_count = int(raw_cache_audit["raw_tensor_class_count_sum"])
    oriented_class_count = int(comm.allreduce(len(schur_cache), op=MPI.SUM))
    if retain_local_schur_for_matrix_free:
        for schur in schur_cache.values():
            schur.setflags(write=False)
        retained_class_count_local = len(schur_cache)
        retained_bytes_local = sum(
            int(schur.nbytes) for schur in schur_cache.values()
        )
        retained_class_count_sum = int(
            comm.allreduce(retained_class_count_local, op=MPI.SUM)
        )
        retained_bytes_sum = int(
            comm.allreduce(retained_bytes_local, op=MPI.SUM)
        )
    else:
        retained_class_count_local = 0
        retained_bytes_local = 0
        retained_class_count_sum = 0
        retained_bytes_sum = 0
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
        retained_local_schur_by_class=(
            MappingProxyType(schur_cache)
            if retain_local_schur_for_matrix_free
            else None
        ),
        comm=comm,
        owned_active_rows=len(owned_active),
        owned_appended_rows=local_appended,
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
            "active_full3d_equivalent_dofs": int(
                trace_rows + active_interior_rows
            ),
            "storage_function_space_dofs": int(full_rows),
            "inactive_max_p_rows_retained_in_matrix": False,
            "full_global_matrix_allocated": False,
            "full_trace_matrix_allocated": False,
            "embedded_mpc_slave_identity_rows_allocated": False,
            "assembly_cost_avoided": True,
            "final_matrix_assembly_deferred_for_appended_rows": bool(
                materialize_global_matrix and defer_final_assembly
            ),
            "axis_aligned_affine_geometry_verified": True,
            "retained_local_schur_enabled": bool(
                retain_local_schur_for_matrix_free
            ),
            "retained_local_schur_class_count_local": retained_class_count_local,
            "retained_local_schur_class_count_sum": retained_class_count_sum,
            "retained_local_schur_bytes_local": retained_bytes_local,
            "retained_local_schur_bytes_sum": retained_bytes_sum,
            **raw_cache_audit,
            "oriented_schur_class_count_sum": oriented_class_count,
            "cell_kernel_evaluation_fraction": float(
                raw_class_count / max(global_cells, 1)
            ),
            "kernel_seconds_max": float(
                comm.allreduce(local_kernel_seconds, op=MPI.MAX)
            ),
            "local_schur_seconds_max": float(
                comm.allreduce(local_schur_seconds, op=MPI.MAX)
            ),
            "local_insert_seconds_max": (
                float(comm.allreduce(local_insert_seconds, op=MPI.MAX))
                if materialize_global_matrix
                else None
            ),
            "pre_final_assembly_sync_seconds_max": (
                preassembly_sync_seconds
            ),
            "final_assembly_seconds": final_assembly_seconds,
            "trace_preallocation_seconds": preallocation_audit["build_seconds"],
            "trace_preallocation": preallocation_audit,
            "trace_constraints": trace_constraints.build_audit,
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
        float(relative_tolerance)
        * float(np.max(np.abs(owned_values), initial=0.0)),
    )
    active = condensed.create_augmented_vector()
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


def project_mpc_vector_to_active_trace(
    condensed: AssemblyTimeCondensedSystem,
    full_vector: PETSc.Vec,
    *,
    eliminated_tolerance: float = 1.0e-12,
    eliminated_relative_tolerance: float = (
        1024.0 * np.finfo(np.float64).eps
    ),
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
        int(value)
        for value in condensed.trace_constraints.owned_active_original_dofs
    )
    trace_set = set(
        int(value) for value in condensed.owned_trace_original_dofs
    )
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
        local = float(
            np.max(np.abs(owned_values[mask]), initial=0.0)
        )
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
    offending_mask = (
        (slave_mask & (np.abs(owned_values) > slave_cutoff))
        | (interior_mask & (np.abs(owned_values) > interior_cutoff))
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
        local_match = np.flatnonzero(
            owned_original == first_offending_dof
        )
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
                "eliminated_relative_tolerance": float(
                    eliminated_relative_tolerance
                ),
                "cell_interior_roundoff_units": interior_roundoff_units,
                "first_offending_dof": first_offending_dof,
                "first_offending_entity": first_offending_entity,
                "pass": bool(
                    max_slave <= slave_cutoff
                    and max_interior <= interior_cutoff
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
    "build_unconstrained_assembly_time_condensation",
    "cell_interior_schur_bilinear",
    "condense_unconstrained_vector_to_active_trace",
    "owned_active_support_groups",
    "project_mpc_vector_to_active_trace",
    "recover_owned_cell_interiors",
]
