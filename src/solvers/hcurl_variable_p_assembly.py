"""PETSc trace assembly for inactive-row-free Task035d variable-p cells."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from time import perf_counter
from typing import Any, Protocol, Sequence

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

from src.adaptivity.exact_sequence_variable_p import (
    VariablePReferenceSpace,
    build_variable_p_reference_space,
)
from src.adaptivity.variable_p_entity_map import (
    VariablePCellDofMap,
    VariablePGlobalEntityMap,
)
from src.adaptivity.variable_p_periodic_orbits import (
    VariablePPeriodicConstraintMap,
)

from .hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
    _cell_integral_kernels,
    _cell_tag_array,
    _distributed_trace_preallocation,
    _global_raw_tensor_cache,
)
from .hcurl_variable_p_local import project_p6_local_tensor


class VariablePTraceConstraintMap(Protocol):
    """Structural contract shared by periodic and local-h trace maps."""

    entity_map: VariablePGlobalEntityMap
    entity_blocks: Any
    owned_cells: tuple[Any, ...]
    independent_trace_rows: int
    audit: Any


def _lu_factor_matrix_action(
    factor: tuple[np.ndarray, np.ndarray],
    values: np.ndarray,
) -> np.ndarray:
    """Apply the original matrix represented by SciPy ``lu_factor``."""

    lu, pivots = factor
    dimension = int(lu.shape[0])
    lower = np.tril(lu, k=-1) + np.eye(
        dimension,
        dtype=lu.dtype,
    )
    upper = np.triu(lu)
    permuted = lower @ (upper @ values)
    permutation = np.arange(dimension)
    for row, pivot in enumerate(pivots):
        permutation[[row, int(pivot)]] = permutation[
            [int(pivot), row]
        ]
    return np.ascontiguousarray(
        permuted[np.argsort(permutation)]
    )


def _iteratively_refined_lu_solve(
    factor: tuple[np.ndarray, np.ndarray],
    right_hand_side: np.ndarray,
    *,
    maximum_steps: int = 2,
) -> np.ndarray:
    """Return the best same-precision LU solution after residual refinement."""

    rhs = np.asarray(right_hand_side, dtype=np.complex128)
    best = np.ascontiguousarray(lu_solve(factor, rhs))
    residual = _lu_factor_matrix_action(factor, best) - rhs
    best_norm = float(np.linalg.norm(residual))
    for _step in range(int(maximum_steps)):
        correction = lu_solve(factor, residual)
        candidate = np.ascontiguousarray(best - correction)
        candidate_residual = (
            _lu_factor_matrix_action(factor, candidate) - rhs
        )
        candidate_norm = float(np.linalg.norm(candidate_residual))
        if not np.isfinite(candidate_norm) or candidate_norm >= best_norm:
            break
        best = candidate
        residual = candidate_residual
        best_norm = candidate_norm
    return best


@dataclass(frozen=True)
class VariablePCellRecovery:
    """Local active-field recovery data for one owned cell."""

    cell: VariablePCellDofMap
    space: VariablePReferenceSpace
    class_key: tuple[Any, ...]


@dataclass
class VariablePCondensedTraceSystem:
    """Physically reduced PETSc trace matrix and local recovery caches."""

    matrix: PETSc.Mat
    entity_map: VariablePGlobalEntityMap
    periodic_constraints: VariablePTraceConstraintMap | None
    active_trace_rows: int
    appended_rows: int
    cell_recovery: tuple[VariablePCellRecovery, ...]
    interior_from_trace_by_class: dict[tuple[Any, ...], np.ndarray]
    interior_lu_by_class: dict[
        tuple[Any, ...],
        tuple[np.ndarray, np.ndarray],
    ]
    trace_from_interior_rhs_by_class: dict[
        tuple[Any, ...],
        np.ndarray,
    ]
    build_audit: dict[str, Any]

    @property
    def trace_constraints(self) -> VariablePTraceConstraintMap | None:
        """Return the generalized assembly-time trace constraint map.

        ``periodic_constraints`` remains as a compatibility field for the
        previously qualified periodic-only path.  New local-h code should use
        this neutral alias.
        """

        return self.periodic_constraints

    def destroy(self) -> None:
        self.matrix.destroy()

    def recover_owned_active_cells(
        self,
        trace_values: np.ndarray,
        *,
        active_full_rhs: PETSc.Vec | None = None,
        assembled_active_trace_values: np.ndarray | None = None,
    ) -> tuple[tuple[VariablePCellDofMap, np.ndarray], ...]:
        """Recover active local coefficients for each locally owned cell."""

        trace = np.asarray(trace_values, dtype=np.complex128)
        expected_trace_rows = self.active_trace_rows
        if trace.shape != (expected_trace_rows,):
            raise ValueError("global active trace vector has the wrong size")
        assembled_trace = (
            None
            if assembled_active_trace_values is None
            else np.asarray(
                assembled_active_trace_values,
                dtype=np.complex128,
            )
        )
        if (
            assembled_trace is not None
            and assembled_trace.shape
            != (self.entity_map.active_trace_rows,)
        ):
            raise ValueError(
                "assembled active trace vector has the wrong size"
            )
        rhs_local = None
        if active_full_rhs is not None:
            if active_full_rhs.getSize() != self.entity_map.active_rows:
                raise ValueError("active full RHS has the wrong global size")
            owned_rhs = np.asarray(
                active_full_rhs.getArray(readonly=True),
                dtype=np.complex128,
            ).copy()
            rhs_packets = self.entity_map.mesh.comm.allgather(owned_rhs)
            rhs_local = np.concatenate(rhs_packets)
            if rhs_local.shape != (self.entity_map.active_rows,):
                raise RuntimeError("active RHS ownership packets do not close")
        result: list[tuple[VariablePCellDofMap, np.ndarray]] = []
        periodic_by_cell = (
            {
                cell.global_cell: cell
                for cell in self.periodic_constraints.owned_cells
            }
            if self.periodic_constraints is not None
            else {}
        )
        for recovery in self.cell_recovery:
            cell = recovery.cell
            if assembled_trace is not None:
                local_trace = assembled_trace[cell.trace_rows]
            elif self.periodic_constraints is None:
                local_trace = trace[cell.trace_rows]
            else:
                periodic_cell = periodic_by_cell[cell.global_cell]
                local_trace = (
                    periodic_cell.full_trace_from_independent
                    @ trace[periodic_cell.independent_rows]
                )
            interior = (
                self.interior_from_trace_by_class[recovery.class_key]
                @ local_trace
            )
            if active_full_rhs is not None:
                rows = np.asarray(cell.interior_rows, dtype=np.int64)
                interior += _iteratively_refined_lu_solve(
                    self.interior_lu_by_class[recovery.class_key],
                    rhs_local[rows],
                )
            active = np.zeros(
                recovery.space.hcurl_dimension,
                dtype=np.complex128,
            )
            active[recovery.space.trace_dofs] = local_trace
            active[recovery.space.interior_dofs] = interior
            result.append((cell, active))
        return tuple(result)


def _balanced_counts(total: int, size: int) -> tuple[int, ...]:
    quotient, remainder = divmod(int(total), int(size))
    return tuple(
        quotient + (1 if rank < remainder else 0)
        for rank in range(size)
    )


def _tensor_sha256(tensor: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(tensor).view(np.uint8)
    ).hexdigest()


def _validate_trace_constraints(
    entity_map: VariablePGlobalEntityMap,
    constraints: VariablePTraceConstraintMap,
) -> tuple[Any, ...]:
    comm = entity_map.mesh.comm
    metadata_error: str | None = None
    active_rows = -1
    cells: tuple[Any, ...] = ()
    try:
        if constraints.entity_map is not entity_map:
            raise ValueError(
                "trace constraints must be built from the same entity map"
            )
        if constraints.audit.get("pass") is not True:
            raise ValueError("trace constraint authority has not passed")
        active_rows = int(constraints.independent_trace_rows)
        if not 0 < active_rows <= entity_map.active_trace_rows:
            raise ValueError(
                "trace constraint independent-row count is invalid"
            )
        cells = tuple(constraints.owned_cells)
        if len(cells) != len(entity_map.owned_cells):
            raise RuntimeError(
                "trace constraints do not cover all locally owned cells"
            )
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        metadata_error = f"{type(exc).__name__}: {exc}"
    metadata_packets = comm.allgather((metadata_error, active_rows))
    metadata_failures = [
        f"rank {rank}: {error}"
        for rank, (error, _rows) in enumerate(metadata_packets)
        if error is not None
    ]
    row_counts = {
        int(rows)
        for error, rows in metadata_packets
        if error is None
    }
    if metadata_failures or len(row_counts) != 1:
        detail = (
            metadata_failures[:4]
            if metadata_failures
            else [f"rank row counts disagree: {sorted(row_counts)}"]
        )
        raise ValueError(
            "collective trace constraint metadata validation failed: "
            + "; ".join(detail)
        )

    local_errors: list[str] = []
    locally_used: list[np.ndarray] = []
    for entity_cell, constrained_cell in zip(
        entity_map.owned_cells,
        cells,
        strict=True,
    ):
        try:
            if constrained_cell.global_cell != entity_cell.global_cell:
                raise RuntimeError(
                    "constrained cells differ from entity-map order"
                )
            rows = np.asarray(constrained_cell.independent_rows)
            expansion = np.asarray(
                constrained_cell.full_trace_from_independent
            )
            if (
                rows.ndim != 1
                or not np.issubdtype(rows.dtype, np.integer)
                or len(rows) == 0
                or len(np.unique(rows)) != len(rows)
                or np.any(rows < 0)
                or np.any(rows >= active_rows)
            ):
                raise ValueError(
                    "one constrained cell has invalid independent rows"
                )
            if expansion.shape != (len(entity_cell.trace_rows), len(rows)):
                raise ValueError(
                    "one constrained cell expansion has the wrong shape"
                )
            if not np.all(np.isfinite(expansion)):
                raise ValueError(
                    "one constrained cell expansion contains non-finite values"
                )
            if np.any(
                np.max(np.abs(expansion), axis=1)
                <= np.finfo(np.float64).tiny
            ):
                raise ValueError(
                    "one constrained cell expansion has an empty trace row"
                )
            locally_used.append(np.asarray(rows, dtype=np.int64))
        except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
            local_errors.append(
                f"cell {entity_cell.global_cell}: "
                f"{type(exc).__name__}: {exc}"
            )

    component_gram = getattr(constraints, "component_gram", None)
    try:
        if component_gram is not None:
            if component_gram.shape != (active_rows, active_rows):
                raise ValueError(
                    "trace constraint component Gram has the wrong shape"
                )
            gram_values = (
                component_gram.data
                if hasattr(component_gram, "indptr")
                else np.asarray(component_gram)
            )
            if not np.all(np.isfinite(gram_values)):
                raise ValueError(
                    "trace constraint component Gram is non-finite"
                )
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        local_errors.append(
            f"component Gram: {type(exc).__name__}: {exc}"
        )

    try:
        entity_blocks = constraints.entity_blocks
        block_values = tuple(entity_blocks.values())
    except (AttributeError, TypeError) as exc:
        local_errors.append(
            f"entity block catalog: {type(exc).__name__}: {exc}"
        )
        entity_blocks = {}
        block_values = ()
    for block in block_values:
        try:
            full_rows = np.asarray(block.full_rows)
            independent = np.asarray(block.independent_rows)
            expansion = np.asarray(block.full_from_independent)
            if (
                full_rows.ndim != 1
                or independent.ndim != 1
                or not np.issubdtype(full_rows.dtype, np.integer)
                or not np.issubdtype(independent.dtype, np.integer)
                or np.any(full_rows < 0)
                or np.any(full_rows >= entity_map.active_trace_rows)
                or np.any(independent < 0)
                or np.any(independent >= active_rows)
                or len(np.unique(full_rows)) != len(full_rows)
                or len(np.unique(independent)) != len(independent)
            ):
                raise ValueError(
                    "one constrained entity block has invalid rows"
                )
            if expansion.shape != (len(full_rows), len(independent)):
                raise ValueError(
                    "one constrained entity expansion has the wrong shape"
                )
            if not np.all(np.isfinite(expansion)):
                raise ValueError(
                    "one constrained entity expansion is non-finite"
                )
        except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
            local_errors.append(
                f"entity block: {type(exc).__name__}: {exc}"
            )
    routed_mode_error: str | None = None
    try:
        routed_work_blocks = getattr(
            constraints,
            "work_owned_entity_blocks",
            None,
        )
        local_routed_mode = routed_work_blocks is not None
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        routed_work_blocks = None
        local_routed_mode = False
        routed_mode_error = f"{type(exc).__name__}: {exc}"
    routed_mode_packets = comm.allgather(
        (local_routed_mode, routed_mode_error)
    )
    routed_mode_failures = [
        f"rank {rank}: {error}"
        for rank, (_mode, error) in enumerate(routed_mode_packets)
        if error is not None
    ]
    routed_modes = {mode for mode, error in routed_mode_packets if error is None}
    if routed_mode_failures or len(routed_modes) != 1:
        detail = (
            routed_mode_failures[:4]
            if routed_mode_failures
            else [
                "rank routed modes disagree: "
                + repr([mode for mode, _error in routed_mode_packets])
            ]
        )
        raise ValueError(
            "collective trace constraint routing-mode validation failed: "
            + "; ".join(detail)
        )
    routed_mode = next(iter(routed_modes))
    if not routed_mode:
        work_rows: list[np.ndarray] = []
        for block in block_values:
            try:
                work_rows.append(
                    np.asarray(block.full_rows, dtype=np.int64)
                )
            except (AttributeError, TypeError, ValueError) as exc:
                local_errors.append(
                    f"legacy work block: {type(exc).__name__}: {exc}"
                )
        covered = (
            np.sort(np.concatenate(work_rows))
            if work_rows
            else np.empty(0, dtype=np.int64)
        )
    else:
        try:
            constraint_audit = constraints.audit
            routing_audit = constraint_audit[
                "owner_routed_trace_cache_audit"
            ]
            if not (
                constraint_audit["petsc_constraint_row_ownership_qualified"]
                is True
                and constraint_audit["mpi_ghost_expansion_qualified"] is True
                and constraint_audit["pde_launch_ownership_gate"] is True
                and routing_audit["pass"] is True
                and routing_audit[
                    "dense_global_entity_catalog_replicated"
                ]
                is False
                and routing_audit["request_reply_count_closes"] is True
            ):
                raise ValueError(
                    "owner-routed trace authority has not passed"
                )
        except (KeyError, TypeError, ValueError) as exc:
            local_errors.append(
                f"owner-routed trace audit: {type(exc).__name__}: {exc}"
            )
        try:
            work_block_values = tuple(routed_work_blocks)
        except (TypeError, ValueError, RuntimeError) as exc:
            local_errors.append(
                f"work-owned block catalog: {type(exc).__name__}: {exc}"
            )
            work_block_values = ()
        work_rows: list[np.ndarray] = []
        active_counts = _balanced_counts(
            entity_map.active_trace_rows,
            comm.size,
        )
        active_starts = np.cumsum((0, *active_counts[:-1]))
        for block in work_block_values:
            try:
                identity = (
                    int(block.dimension),
                    int(block.global_entity),
                )
                if entity_blocks.get(identity) is not block:
                    raise ValueError(
                        "one work-owned block is absent from the local cache"
                    )
                owner_rank = int(block.active_vector_work_owner_rank)
                full_rows = np.asarray(block.full_rows, dtype=np.int64)
                first_row = int(full_rows[0])
                expected_owner = next(
                    rank
                    for rank, (start, count) in enumerate(
                        zip(active_starts, active_counts, strict=True)
                    )
                    if int(start) <= first_row < int(start + count)
                )
                if owner_rank != comm.rank or owner_rank != expected_owner:
                    raise ValueError(
                        "one routed block has the wrong active-vector owner"
                    )
                work_rows.append(full_rows)
            except (
                AttributeError,
                IndexError,
                StopIteration,
                TypeError,
                ValueError,
            ) as exc:
                local_errors.append(
                    f"work-owned entity block: {type(exc).__name__}: {exc}"
                )
        local_work_rows = (
            np.concatenate(work_rows)
            if work_rows
            else np.empty(0, dtype=np.int64)
        )
        covered = np.sort(
            np.concatenate(comm.allgather(local_work_rows))
        )
    if not np.array_equal(
        covered,
        np.arange(entity_map.active_trace_rows, dtype=np.int64),
    ):
        local_errors.append(
            "trace entity blocks do not partition unconstrained trace rows"
        )

    for entity_cell, constrained_cell in zip(
        entity_map.owned_cells,
        cells,
        strict=True,
    ):
        try:
            blocks: list[Any] = []
            for dimension in (1, 2):
                index_map = entity_map.mesh.topology.index_map(dimension)
                global_entities = np.asarray(
                    index_map.local_to_global(
                        np.asarray(
                            entity_cell.entity_ids[dimension],
                            dtype=np.int32,
                        )
                    ),
                    dtype=np.int64,
                )
                blocks.extend(
                    entity_blocks[
                        (dimension, int(global_entity))
                    ]
                    for global_entity in global_entities
                )
            full_rows = np.concatenate(
                [np.asarray(block.full_rows) for block in blocks]
            )
            if not np.array_equal(full_rows, entity_cell.trace_rows):
                raise RuntimeError(
                    "entity blocks differ from cell trace row order"
                )
            independent = np.unique(
                np.concatenate(
                    [
                        np.asarray(block.independent_rows)
                        for block in blocks
                    ]
                )
            ).astype(np.int64)
            column = {
                int(row): index for index, row in enumerate(independent)
            }
            reconstructed = np.zeros(
                (len(full_rows), len(independent)),
                dtype=np.complex128,
            )
            row_start = 0
            for block in blocks:
                block_rows = np.asarray(block.full_rows)
                block_independent = np.asarray(block.independent_rows)
                row_stop = row_start + len(block_rows)
                columns = np.asarray(
                    [column[int(row)] for row in block_independent],
                    dtype=np.int64,
                )
                reconstructed[
                    np.ix_(np.arange(row_start, row_stop), columns)
                ] = np.asarray(block.full_from_independent)
                row_start = row_stop
            if not np.array_equal(
                independent,
                constrained_cell.independent_rows,
            ):
                raise RuntimeError(
                    "cell and entity blocks use different independent rows"
                )
            mismatch = float(
                np.max(
                    np.abs(
                        reconstructed
                        - constrained_cell.full_trace_from_independent
                    ),
                    initial=0.0,
                )
            )
            if mismatch > 5.0e-11:
                raise RuntimeError(
                    "cell and entity trace expansions disagree: "
                    f"{mismatch:.6e}"
                )
        except (
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            RuntimeError,
        ) as exc:
            local_errors.append(
                f"cell/entity cross-check {entity_cell.global_cell}: "
                f"{type(exc).__name__}: {exc}"
            )

    error_packets = comm.allgather(tuple(local_errors))
    collective_errors = [
        f"rank {rank}: {error}"
        for rank, packet in enumerate(error_packets)
        for error in packet
    ]
    if collective_errors:
        raise ValueError(
            "collective trace constraint validation failed: "
            + "; ".join(collective_errors[:4])
        )

    local_union = (
        np.unique(np.concatenate(locally_used))
        if locally_used
        else np.empty(0, dtype=np.int64)
    )
    global_union = np.unique(
        np.concatenate(comm.allgather(local_union))
    )
    if not np.array_equal(
        global_union,
        np.arange(active_rows, dtype=np.int64),
    ):
        raise RuntimeError(
            "trace constraint map contains an isolated independent row"
        )
    return cells


def build_variable_p_condensed_trace_system(
    entity_map: VariablePGlobalEntityMap,
    p6_tensors_by_owned_cell: Sequence[np.ndarray],
    *,
    tensor_class_keys: Sequence[Any] | None = None,
    periodic_constraints: VariablePPeriodicConstraintMap | None = None,
    trace_constraints: VariablePTraceConstraintMap | None = None,
    appended_global_rows: int = 0,
    appended_support_owned_cell_groups: tuple[np.ndarray, ...] = (),
    appended_support_group_by_row: tuple[int, ...] = (),
    defer_final_assembly: bool = False,
) -> VariablePCondensedTraceSystem:
    """Project p6 cell tensors, condense interiors, and assemble active rows."""

    comm = entity_map.mesh.comm
    appended_global_rows = int(appended_global_rows)
    if appended_global_rows < 0:
        raise ValueError("appended global rows must be non-negative")
    if appended_global_rows and not defer_final_assembly:
        raise ValueError(
            "appended rows require deferred final assembly by the caller"
        )
    cells = entity_map.owned_cells
    tensors = tuple(np.asarray(tensor) for tensor in p6_tensors_by_owned_cell)
    if len(tensors) != len(cells):
        raise ValueError("one p6 tensor is required per locally owned cell")
    if tensor_class_keys is None:
        raw_keys = tuple(_tensor_sha256(tensor) for tensor in tensors)
    else:
        raw_keys = tuple(tensor_class_keys)
        if len(raw_keys) != len(cells):
            raise ValueError("tensor class keys do not match owned cells")
    p6_dimension = 882
    for tensor in tensors:
        if tensor.shape != (p6_dimension, p6_dimension):
            raise ValueError("variable-p assembly requires p6 hexa cell tensors")
        if not np.all(np.isfinite(tensor)):
            raise ValueError("p6 cell tensor contains non-finite entries")
    if periodic_constraints is not None and trace_constraints is not None:
        raise ValueError(
            "supply periodic_constraints or trace_constraints, not both"
        )
    constraints: VariablePTraceConstraintMap | None = (
        trace_constraints
        if trace_constraints is not None
        else periodic_constraints
    )
    constrained_cells = (
        _validate_trace_constraints(entity_map, constraints)
        if constraints is not None
        else (None,) * len(cells)
    )

    started = perf_counter()
    active_rows = (
        constraints.independent_trace_rows
        if constraints is not None
        else entity_map.active_trace_rows
    )
    matrix_rows = active_rows + appended_global_rows
    local_appended = (
        appended_global_rows if comm.rank == comm.size - 1 else 0
    )
    insertion_rows = tuple(
        constrained_cell.independent_rows
        if constrained_cell is not None
        else cell.trace_rows
        for cell, constrained_cell in zip(
            cells,
            constrained_cells,
            strict=True,
        )
    )
    active_counts = _balanced_counts(active_rows, comm.size)
    active_start = int(sum(active_counts[: comm.rank]))
    preallocation_started = perf_counter()
    diagonal_nnz, off_diagonal_nnz, preallocation = (
        _distributed_trace_preallocation(
            comm,
            insertion_rows,
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
    preallocation_seconds = float(
        comm.allreduce(
            perf_counter() - preallocation_started,
            op=MPI.MAX,
        )
    )
    matrix = PETSc.Mat().createAIJ(
        size=(
            (
                active_counts[comm.rank] + local_appended,
                matrix_rows,
            ),
            (
                active_counts[comm.rank] + local_appended,
                matrix_rows,
            ),
        ),
        nnz=(
            diagonal_nnz
            if comm.size == 1
            else (diagonal_nnz, off_diagonal_nnz)
        ),
        comm=comm,
    )
    if matrix.getOwnershipRange()[0] != active_start:
        matrix.destroy()
        raise RuntimeError("PETSc ownership differs from active row partition")
    matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)

    schur_cache: dict[tuple[Any, ...], np.ndarray] = {}
    interior_from_trace: dict[tuple[Any, ...], np.ndarray] = {}
    interior_lu: dict[
        tuple[Any, ...],
        tuple[np.ndarray, np.ndarray],
    ] = {}
    trace_from_interior_rhs: dict[tuple[Any, ...], np.ndarray] = {}
    recoveries: list[VariablePCellRecovery] = []
    projection_seconds = 0.0
    condensation_seconds = 0.0
    insertion_seconds = 0.0
    interior_recovery_operator_residual = 0.0
    interior_adjoint_operator_residual = 0.0
    for cell, p6_tensor, raw_key, constrained_cell in zip(
        cells,
        tensors,
        raw_keys,
        constrained_cells,
        strict=True,
    ):
        space = build_variable_p_reference_space(cell.degree_map)
        class_key = (
            raw_key,
            cell.degree_map.signature,
            int(cell.cell_info),
        )
        schur = schur_cache.get(class_key)
        if schur is None:
            projection_started = perf_counter()
            active_tensor = project_p6_local_tensor(space, p6_tensor)
            oriented = space.orient_hcurl_tensor(
                active_tensor,
                cell_info=cell.cell_info,
            )
            projection_seconds += perf_counter() - projection_started
            condensation_started = perf_counter()
            trace_positions = np.asarray(space.trace_dofs, dtype=np.int32)
            interior_positions = np.asarray(
                space.interior_dofs,
                dtype=np.int32,
            )
            A_tt = oriented[
                np.ix_(trace_positions, trace_positions)
            ]
            A_ti = oriented[
                np.ix_(trace_positions, interior_positions)
            ]
            A_it = oriented[
                np.ix_(interior_positions, trace_positions)
            ]
            A_ii = oriented[
                np.ix_(interior_positions, interior_positions)
            ]
            factor = lu_factor(A_ii)
            recovery = -lu_solve(factor, A_it)
            adjoint_solution = lu_solve(
                factor,
                A_ti.conj().T,
                trans=2,
            )
            trace_rhs = -adjoint_solution.conj().T
            recovery_residual = A_ii @ recovery + A_it
            recovery_scale = max(
                float(np.max(np.abs(A_it), initial=0.0)),
                1.0,
            )
            interior_recovery_operator_residual = max(
                interior_recovery_operator_residual,
                float(
                    np.max(
                        np.abs(recovery_residual),
                        initial=0.0,
                    )
                    / recovery_scale
                ),
            )
            adjoint_residual = (
                A_ii.conj().T @ adjoint_solution
                - A_ti.conj().T
            )
            adjoint_scale = max(
                float(np.max(np.abs(A_ti), initial=0.0)),
                1.0,
            )
            interior_adjoint_operator_residual = max(
                interior_adjoint_operator_residual,
                float(
                    np.max(
                        np.abs(adjoint_residual),
                        initial=0.0,
                    )
                    / adjoint_scale
                ),
            )
            schur = np.ascontiguousarray(A_tt + A_ti @ recovery)
            condensation_seconds += perf_counter() - condensation_started
            schur_cache[class_key] = schur
            interior_from_trace[class_key] = recovery
            interior_lu[class_key] = factor
            trace_from_interior_rhs[class_key] = trace_rhs
        insertion_started = perf_counter()
        if constrained_cell is None:
            rows = cell.trace_rows
            insertion_tensor = schur
        else:
            expansion = constrained_cell.full_trace_from_independent
            rows = constrained_cell.independent_rows
            insertion_tensor = (
                expansion.conj().T @ schur @ expansion
            )
        matrix.setValues(
            np.asarray(rows, dtype=PETSc.IntType),
            np.asarray(rows, dtype=PETSc.IntType),
            np.asarray(insertion_tensor, dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.ADD_VALUES,
        )
        insertion_seconds += perf_counter() - insertion_started
        recoveries.append(
            VariablePCellRecovery(
                cell=cell,
                space=space,
                class_key=class_key,
            )
        )
    if defer_final_assembly:
        assembly_seconds = 0.0
        info: dict[str, float] = {}
    else:
        assembly_started = perf_counter()
        matrix.assemble()
        assembly_seconds = float(
            comm.allreduce(
                perf_counter() - assembly_started,
                op=MPI.MAX,
            )
        )
        info = matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
    matrix_rows, matrix_columns = matrix.getSize()
    expected_nnz = int(preallocation["preallocated_structural_nnz"])
    actual_nnz = (
        None
        if defer_final_assembly
        else int(round(float(info.get("nz_used", 0.0))))
    )
    if (
        matrix_rows != active_rows + appended_global_rows
        or matrix_columns != active_rows + appended_global_rows
        or (
            not defer_final_assembly
            and actual_nnz != expected_nnz
        )
    ):
        matrix.destroy()
        raise RuntimeError(
            "variable-p PETSc matrix does not match the exact active graph"
        )
    recovery_operator_residual = float(
        comm.allreduce(
            interior_recovery_operator_residual,
            op=MPI.MAX,
        )
    )
    adjoint_operator_residual = float(
        comm.allreduce(
            interior_adjoint_operator_residual,
            op=MPI.MAX,
        )
    )
    if (
        recovery_operator_residual > 5.0e-11
        or adjoint_operator_residual > 5.0e-11
    ):
        matrix.destroy()
        raise RuntimeError(
            "cell-interior recovery operator failed residual Gate: "
            f"primal={recovery_operator_residual:.6e}, "
            f"adjoint={adjoint_operator_residual:.6e}"
        )
    global_cells = int(comm.allreduce(len(cells), op=MPI.SUM))
    constraint_kinds = (
        set()
        if constraints is None
        else set(map(str, constraints.audit.get("constraint_kinds", ())))
    )
    if (
        constraints is not None
        and not constraint_kinds
        and isinstance(constraints, VariablePPeriodicConstraintMap)
    ):
        constraint_kinds = {"floquet"}
    contains_floquet = "floquet" in constraint_kinds
    contains_hanging = "hanging" in constraint_kinds
    constraint_schema = (
        None
        if constraints is None
        else str(constraints.audit.get("schema_version", "unknown"))
    )
    eliminated_trace_rows = int(
        entity_map.active_trace_rows - active_rows
    )
    audit = {
        "schema_version": "task035d.variable-p-condensed-trace-system.v1",
        "status": "variable_p_condensed_trace_matrix_pass",
        "pass": True,
        "mpi_size": int(comm.size),
        "global_cell_count": global_cells,
        "active_full3d_rows_before_condensation": entity_map.active_rows,
        "active_trace_rows_before_periodic_elimination": (
            entity_map.active_trace_rows
        ),
        "active_trace_rows_before_constraint_elimination": (
            entity_map.active_trace_rows
        ),
        "active_trace_rows": active_rows,
        "appended_rows": appended_global_rows,
        "periodic_slave_rows": int(
            constraints.audit.get(
                "periodic_slave_rows",
                eliminated_trace_rows,
            )
        )
        if contains_floquet
        else (0 if constraints is None else None),
        "hanging_slave_rows": int(
            constraints.audit.get("hanging_slave_rows", 0)
        )
        if contains_hanging
        else 0,
        "hanging_or_floquet_slave_rows": eliminated_trace_rows,
        "floquet_elimination_applied_before_insertion": (
            contains_floquet
        ),
        "hanging_elimination_applied_before_insertion": (
            contains_hanging
        ),
        "trace_constraint_elimination_applied_before_insertion": (
            constraints is not None
        ),
        "trace_constraint_kinds": sorted(constraint_kinds),
        "trace_constraint_schema": constraint_schema,
        "trace_constraint_owner_routing_qualified": (
            None
            if constraints is None
            else constraints.audit.get("pde_launch_ownership_gate")
        ),
        "trace_constraint_dense_global_entity_catalog_replicated": (
            None
            if constraints is None
            else constraints.audit.get(
                "owner_routed_trace_cache_audit",
                {},
            ).get("dense_global_entity_catalog_replicated")
        ),
        "trace_constraint_distributed_scalability_qualified": (
            None
            if constraints is None
            else constraints.audit.get("distributed_scalability_qualified")
        ),
        "uniform_p6_full3d_rows": entity_map.uniform_p6_rows,
        "uniform_p6_trace_rows": entity_map.uniform_p6_trace_rows,
        "inactive_p6_full_rows": int(
            entity_map.uniform_p6_rows - entity_map.active_rows
        ),
        "inactive_p6_trace_rows": int(
            entity_map.uniform_p6_trace_rows
            - entity_map.active_trace_rows
        ),
        "matrix_rows": int(matrix_rows),
        "matrix_nnz": actual_nnz,
        "matrix_nnz_preallocated": expected_nnz,
        "matrix_nnz_allocated": int(
            round(float(info.get("nz_allocated", 0.0)))
        ),
        "matrix_mallocs": int(
            round(float(info.get("mallocs", 0.0)))
        )
        if not defer_final_assembly
        else None,
        "local_reference_class_count_sum": int(
            comm.allreduce(len(schur_cache), op=MPI.SUM)
        ),
        "projection_seconds_max": float(
            comm.allreduce(projection_seconds, op=MPI.MAX)
        ),
        "condensation_seconds_max": float(
            comm.allreduce(condensation_seconds, op=MPI.MAX)
        ),
        "insertion_seconds_max": float(
            comm.allreduce(insertion_seconds, op=MPI.MAX)
        ),
        "interior_recovery_operator_residual_max": float(
            recovery_operator_residual
        ),
        "interior_adjoint_operator_residual_max": float(
            adjoint_operator_residual
        ),
        "interior_rhs_recovery_iterative_refinement_max_steps": 2,
        "interior_rhs_recovery_refinement_uses_retained_lu_only": True,
        "final_assembly_seconds": assembly_seconds,
        "final_assembly_deferred": bool(defer_final_assembly),
        "preallocation_seconds": preallocation_seconds,
        "total_build_seconds": float(
            comm.allreduce(perf_counter() - started, op=MPI.MAX)
        ),
        "trace_preallocation": preallocation,
        "full_p6_global_matrix_constructed": False,
        "full_active_global_matrix_constructed": False,
        "inactive_p6_rows_globally_numbered": False,
        "periodic_slave_rows_globally_numbered": False,
        "trace_slave_rows_globally_numbered": False,
        "hanging_or_floquet_slave_rows_globally_numbered": False,
        "trace_constraint_cell_tensor_binding_complete": (
            constraints is not None
        ),
        "cell_p6_tensors_are_local_only": True,
        "ordinary_default_changed": False,
    }
    return VariablePCondensedTraceSystem(
        matrix=matrix,
        entity_map=entity_map,
        periodic_constraints=constraints,
        active_trace_rows=active_rows,
        appended_rows=appended_global_rows,
        cell_recovery=tuple(recoveries),
        interior_from_trace_by_class=interior_from_trace,
        interior_lu_by_class=interior_lu,
        trace_from_interior_rhs_by_class=trace_from_interior_rhs,
        build_audit=audit,
    )


def build_variable_p_condensed_trace_system_from_compiled_form(
    compiled_form: Any,
    p6_space: Any,
    cell_tags: Any,
    entity_map: VariablePGlobalEntityMap,
    *,
    periodic_constraints: VariablePPeriodicConstraintMap | None = None,
    trace_constraints: VariablePTraceConstraintMap | None = None,
    appended_global_rows: int = 0,
    appended_support_owned_cell_groups: tuple[np.ndarray, ...] = (),
    appended_support_group_by_row: tuple[int, ...] = (),
    defer_final_assembly: bool = False,
    geometry_tolerance: float = 1.0e-11,
) -> VariablePCondensedTraceSystem:
    """Evaluate p6 FFCx tensor classes and assemble the true active system."""

    if periodic_constraints is not None and trace_constraints is not None:
        raise ValueError(
            "supply periodic_constraints or trace_constraints, not both"
        )
    if np.dtype(compiled_form.dtype) != np.dtype(np.complex128):
        raise TypeError("variable-p compiled form must use complex128")
    if p6_space.mesh is not entity_map.mesh:
        raise ValueError(
            "compiled p6 space and variable-p entity map use different meshes"
        )
    element = p6_space.element.basix_element
    if (
        int(element.dim) != 882
        or "hexahedron" not in str(element.cell_type).lower()
        or "covariant" not in str(element.map_type).lower()
    ):
        raise ValueError(
            "variable-p compiled builder requires hexahedral N1curl p6"
        )
    form_spaces = tuple(compiled_form.function_spaces)
    p6_cpp_mesh = getattr(
        p6_space.mesh,
        "_cpp_object",
        p6_space.mesh,
    )
    if not form_spaces or any(
        space.mesh is not p6_cpp_mesh for space in form_spaces
    ):
        raise ValueError("compiled form uses a different finite-element mesh")
    if any(
        int(space.element.basix_element.hash()) != int(element.hash())
        for space in form_spaces
    ):
        raise ValueError("compiled form is not the supplied p6 space")

    msh = entity_map.mesh
    comm = msh.comm
    owned_cells = int(msh.topology.index_map(3).size_local)
    if owned_cells != len(entity_map.owned_cells):
        raise RuntimeError("variable-p entity map misses owned mesh cells")
    tags = _cell_tag_array(cell_tags, owned_cells)
    kernels = _cell_integral_kernels(compiled_form)
    unknown_tags = (
        []
        if -1 in kernels
        else sorted(set(map(int, tags)) - set(kernels))
    )
    if unknown_tags:
        raise ValueError(
            f"compiled p6 form has no cell integral for tags {unknown_tags}"
        )

    metadata_started = perf_counter()
    coordinates_by_class: dict[tuple[Any, ...], np.ndarray] = {}
    cell_policy_keys: list[tuple[Any, ...]] = []
    tensor_keys: list[tuple[Any, ...]] = []
    for cell in range(owned_cells):
        coordinates, widths = _canonical_axis_aligned_coordinates(
            msh,
            cell,
            tolerance=float(geometry_tolerance),
        )
        tag = int(tags[cell])
        policy_key = ("p6_actual_space", tag, *widths)
        previous = coordinates_by_class.get(policy_key)
        if previous is not None and not np.array_equal(
            previous,
            coordinates,
        ):
            raise RuntimeError(
                "p6 tensor class has inconsistent canonical coordinates"
            )
        coordinates_by_class.setdefault(policy_key, coordinates)
        cell_policy_keys.append(policy_key)
        tensor_keys.append((tag, *widths))
    metadata_seconds = float(
        comm.allreduce(
            perf_counter() - metadata_started,
            op=MPI.MAX,
        )
    )
    raw_cache, raw_audit, local_kernel_seconds = (
        _global_raw_tensor_cache(
            comm,
            coordinates_by_class,
            {
                "p6_actual_space": (
                    compiled_form,
                    kernels,
                    882,
                )
            },
        )
    )
    system = build_variable_p_condensed_trace_system(
        entity_map,
        tuple(raw_cache[key] for key in cell_policy_keys),
        tensor_class_keys=tuple(tensor_keys),
        periodic_constraints=periodic_constraints,
        trace_constraints=trace_constraints,
        appended_global_rows=appended_global_rows,
        appended_support_owned_cell_groups=(
            appended_support_owned_cell_groups
        ),
        appended_support_group_by_row=(
            appended_support_group_by_row
        ),
        defer_final_assembly=defer_final_assembly,
    )
    system.build_audit.update(
        {
            "compiled_p6_tensor_builder": True,
            "compiled_trace_constraint_binding_complete": (
                system.trace_constraints is not None
            ),
            "compiled_p6_form_dtype": str(
                np.dtype(compiled_form.dtype)
            ),
            "compiled_p6_element_hash": int(element.hash()),
            "raw_tensor_metadata_seconds": metadata_seconds,
            "raw_tensor_kernel_seconds_max": float(
                comm.allreduce(local_kernel_seconds, op=MPI.MAX)
            ),
            **raw_audit,
        }
    )
    return system


def _global_active_vector_values(
    system: VariablePCondensedTraceSystem,
    vector: PETSc.Vec,
) -> np.ndarray:
    if vector.getSize() != system.entity_map.active_rows:
        raise ValueError("active full vector has the wrong global size")
    owned = np.asarray(
        vector.getArray(readonly=True),
        dtype=np.complex128,
    ).copy()
    values = np.concatenate(system.entity_map.mesh.comm.allgather(owned))
    if values.shape != (system.entity_map.active_rows,):
        raise RuntimeError("active vector ownership packets do not close")
    if not np.all(np.isfinite(values)):
        raise ValueError("active full vector contains non-finite entries")
    return values


def condense_variable_p_active_vector_to_trace(
    system: VariablePCondensedTraceSystem,
    active_full_vector: PETSc.Vec,
    *,
    side: str,
    relative_tolerance: float = 1.0e-14,
) -> PETSc.Vec:
    """Apply local Schur and Floquet reductions to an active full vector."""

    if side not in {"right", "left"}:
        raise ValueError("vector condensation side must be right or left")
    comm = system.entity_map.mesh.comm
    values = _global_active_vector_values(system, active_full_vector)
    cutoff = max(
        1.0e-30,
        float(relative_tolerance)
        * float(np.max(np.abs(values), initial=0.0)),
    )
    target = system.matrix.createVecRight()
    row_start, row_end = map(
        int,
        active_full_vector.getOwnershipRange(),
    )
    if system.periodic_constraints is None:
        start = max(row_start, 0)
        stop = min(row_end, system.entity_map.active_trace_rows)
        if stop > start:
            rows = np.arange(start, stop, dtype=PETSc.IntType)
            retained = np.abs(values[start:stop]) > cutoff
            target.setValues(
                rows[retained],
                np.asarray(
                    values[start:stop][retained],
                    dtype=PETSc.ScalarType,
                ),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
        periodic_by_cell: dict[int, Any] = {}
    else:
        constraints = system.periodic_constraints
        periodic_by_cell = {
            cell.global_cell: cell for cell in constraints.owned_cells
        }
        routed_blocks = getattr(
            constraints,
            "work_owned_entity_blocks",
            None,
        )
        for block in (
            routed_blocks
            if routed_blocks is not None
            else constraints.entity_blocks.values()
        ):
            if routed_blocks is None:
                if not (
                    row_start <= int(block.full_rows[0]) < row_end
                ):
                    continue
            elif int(block.active_vector_work_owner_rank) != comm.rank:
                raise RuntimeError(
                    "routed trace block reached the wrong work owner"
                )
            projected = (
                block.full_from_independent.conj().T
                @ values[block.full_rows]
            )
            retained = np.abs(projected) > cutoff
            target.setValues(
                np.asarray(
                    block.independent_rows[retained],
                    dtype=PETSc.IntType,
                ),
                np.asarray(
                    projected[retained],
                    dtype=PETSc.ScalarType,
                ),
                addv=PETSc.InsertMode.ADD_VALUES,
            )

    for recovery in system.cell_recovery:
        interior_values = values[recovery.cell.interior_rows]
        if (
            float(
                np.max(np.abs(interior_values), initial=0.0)
            )
            <= cutoff
        ):
            continue
        if side == "right":
            correction = (
                system.trace_from_interior_rhs_by_class[
                    recovery.class_key
                ]
                @ interior_values
            )
        else:
            correction = (
                system.interior_from_trace_by_class[
                    recovery.class_key
                ].conj().T
                @ interior_values
            )
        if system.periodic_constraints is None:
            rows = recovery.cell.trace_rows
        else:
            periodic_cell = periodic_by_cell[
                recovery.cell.global_cell
            ]
            correction = (
                periodic_cell.full_trace_from_independent.conj().T
                @ correction
            )
            rows = periodic_cell.independent_rows
        retained = np.abs(correction) > cutoff
        target.setValues(
            np.asarray(rows[retained], dtype=PETSc.IntType),
            np.asarray(
                correction[retained],
                dtype=PETSc.ScalarType,
            ),
            addv=PETSc.InsertMode.ADD_VALUES,
        )
    target.assemble()
    return target


def variable_p_cell_interior_schur_bilinear(
    system: VariablePCondensedTraceSystem,
    left_active_full: PETSc.Vec,
    right_active_full: PETSc.Vec,
) -> complex:
    """Return the eliminated active-interior cross bilinear."""

    left = _global_active_vector_values(system, left_active_full)
    right = _global_active_vector_values(system, right_active_full)
    local = 0.0 + 0.0j
    for recovery in system.cell_recovery:
        rows = recovery.cell.interior_rows
        left_values = left[rows]
        right_values = right[rows]
        if not np.any(left_values) or not np.any(right_values):
            continue
        local += np.vdot(
            left_values,
            lu_solve(
                system.interior_lu_by_class[recovery.class_key],
                right_values,
            ),
        )
    return complex(
        system.entity_map.mesh.comm.allreduce(local, op=MPI.SUM)
    )


def recover_variable_p_active_full_vector(
    system: VariablePCondensedTraceSystem,
    trace_values: PETSc.Vec | np.ndarray,
    *,
    active_full_rhs: PETSc.Vec | None = None,
) -> PETSc.Vec:
    """Recover the conforming full active coefficient vector."""

    if isinstance(trace_values, PETSc.Vec):
        owned = np.asarray(
            trace_values.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        supplied = np.concatenate(
            system.entity_map.mesh.comm.allgather(owned)
        )
    else:
        supplied = np.asarray(trace_values, dtype=np.complex128)
    if supplied.shape == (system.matrix.getSize()[0],):
        trace = supplied[: system.active_trace_rows]
    elif supplied.shape == (system.active_trace_rows,):
        trace = supplied
    else:
        raise ValueError("reduced trace vector has the wrong global size")

    comm = system.entity_map.mesh.comm
    active_counts = _balanced_counts(
        system.entity_map.active_rows,
        comm.size,
    )
    recovered = PETSc.Vec().createMPI(
        (
            active_counts[comm.rank],
            system.entity_map.active_rows,
        ),
        comm=comm,
    )
    recovered.set(PETSc.ScalarType(0.0))
    row_start, row_end = map(int, recovered.getOwnershipRange())
    if system.periodic_constraints is None:
        start = max(row_start, 0)
        stop = min(row_end, system.entity_map.active_trace_rows)
        if stop > start:
            recovered.setValues(
                np.arange(start, stop, dtype=PETSc.IntType),
                np.asarray(
                    trace[start:stop],
                    dtype=PETSc.ScalarType,
                ),
                addv=PETSc.InsertMode.INSERT_VALUES,
            )
    else:
        constraints = system.periodic_constraints
        routed_blocks = getattr(
            constraints,
            "work_owned_entity_blocks",
            None,
        )
        for block in (
            routed_blocks
            if routed_blocks is not None
            else constraints.entity_blocks.values()
        ):
            if routed_blocks is None:
                if not (
                    row_start <= int(block.full_rows[0]) < row_end
                ):
                    continue
            elif int(block.active_vector_work_owner_rank) != comm.rank:
                raise RuntimeError(
                    "routed trace block reached the wrong work owner"
                )
            values = (
                block.full_from_independent
                @ trace[block.independent_rows]
            )
            recovered.setValues(
                np.asarray(block.full_rows, dtype=PETSc.IntType),
                np.asarray(values, dtype=PETSc.ScalarType),
                addv=PETSc.InsertMode.INSERT_VALUES,
            )
    recovered.assemble()
    assembled_active_trace = _global_active_vector_values(
        system,
        recovered,
    )[: system.entity_map.active_trace_rows].copy()
    for cell, local_active in system.recover_owned_active_cells(
        trace,
        active_full_rhs=active_full_rhs,
        assembled_active_trace_values=assembled_active_trace,
    ):
        space = build_variable_p_reference_space(cell.degree_map)
        recovered.setValues(
            np.asarray(cell.interior_rows, dtype=PETSc.IntType),
            np.asarray(
                local_active[space.interior_dofs],
                dtype=PETSc.ScalarType,
            ),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    recovered.assemble()
    return recovered


__all__ = [
    "VariablePCellRecovery",
    "VariablePCondensedTraceSystem",
    "build_variable_p_condensed_trace_system",
    "build_variable_p_condensed_trace_system_from_compiled_form",
    "condense_variable_p_active_vector_to_trace",
    "recover_variable_p_active_full_vector",
    "variable_p_cell_interior_schur_bilinear",
]
