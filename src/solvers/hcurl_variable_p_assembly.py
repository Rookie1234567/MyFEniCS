"""PETSc trace assembly for inactive-row-free Task035d variable-p cells."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from time import perf_counter
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

from src.adaptivity.exact_sequence_variable_p import (
    VariablePReferenceSpace,
    build_variable_p_reference_space,
)
from src.adaptivity.variable_p_transfer import PETScSelectedRowLayout
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
    *,
    trans: int = 0,
) -> np.ndarray:
    """Apply the factored matrix or its Hermitian transpose."""

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
    if trans == 0:
        return np.ascontiguousarray(
            permuted[np.argsort(permutation)]
        )
    if trans == 2:
        rhs = np.asarray(values)[permutation]
        return np.ascontiguousarray(
            upper.conj().T @ (lower.conj().T @ rhs)
        )
    raise ValueError("factored matrix action supports trans=0 or trans=2")


def _iteratively_refined_lu_solve(
    factor: tuple[np.ndarray, np.ndarray],
    right_hand_side: np.ndarray,
    *,
    maximum_steps: int = 2,
    trans: int = 0,
) -> np.ndarray:
    """Return the best same-precision LU solution after residual refinement."""

    rhs = np.asarray(right_hand_side, dtype=np.complex128)
    if trans not in {0, 2}:
        raise ValueError("iterative LU solve supports trans=0 or trans=2")
    best = np.ascontiguousarray(lu_solve(factor, rhs, trans=trans))
    residual = (
        _lu_factor_matrix_action(factor, best, trans=trans) - rhs
    )
    best_norm = float(np.linalg.norm(residual))
    for _step in range(int(maximum_steps)):
        correction = lu_solve(factor, residual, trans=trans)
        candidate = np.ascontiguousarray(best - correction)
        candidate_residual = (
            _lu_factor_matrix_action(
                factor,
                candidate,
                trans=trans,
            )
            - rhs
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


@dataclass(frozen=True)
class VariablePOwnedCellSchurAction:
    """One owned cell's pre-constraint trace and condensed action."""

    local_cell: int
    global_cell: int
    cell_info: int
    degree_signature: str
    trace_rows: np.ndarray
    local_trace_values: np.ndarray
    local_condensed_action: np.ndarray


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
    retained_local_schur_by_class: (
        Mapping[tuple[Any, ...], np.ndarray] | None
    )
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
        self.release_retained_local_schur()
        self.matrix.destroy()

    def release_retained_local_schur(self) -> dict[str, Any]:
        """Release the explicit research-only local Schur lease."""

        retained = self.retained_local_schur_by_class
        requested = bool(
            self.build_audit.get(
                "retain_local_schur_for_research_requested",
                False,
            )
        )
        previously_released = bool(
            self.build_audit.get(
                "retained_local_schur_released",
                False,
            )
        )
        local_class_count = 0 if retained is None else len(retained)
        local_bytes = (
            0
            if retained is None
            else int(sum(value.nbytes for value in retained.values()))
        )
        self.retained_local_schur_by_class = None
        self.build_audit.update(
            {
                "retained_local_schur_active": False,
                "retained_local_schur_released": bool(
                    requested
                    and (retained is not None or previously_released)
                ),
            }
        )
        return {
            "schema_version": (
                "task035d.variable-p-local-schur-release.v1"
            ),
            "status": (
                "retained_local_schur_released"
                if retained is not None
                else "no_active_retained_local_schur"
            ),
            "pass": True,
            "local_class_count_released": local_class_count,
            "local_bytes_released": local_bytes,
            "ordinary_default_changed": False,
        }

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

    def recover_owned_active_adjoint_cells(
        self,
        trace_values: np.ndarray,
        *,
        active_full_goal: PETSc.Vec | None = None,
        assembled_active_trace_values: np.ndarray | None = None,
    ) -> tuple[tuple[VariablePCellDofMap, np.ndarray], ...]:
        """Recover local adjoints with the exact conjugate-transpose Schur map."""

        trace = np.asarray(trace_values, dtype=np.complex128)
        if trace.shape != (self.active_trace_rows,):
            raise ValueError("global reduced adjoint trace has the wrong size")
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
                "assembled active adjoint trace has the wrong size"
            )
        goal_values = None
        if active_full_goal is not None:
            goal_values = _global_active_vector_values(
                self,
                active_full_goal,
            )
        constrained_by_cell = (
            {
                cell.global_cell: cell
                for cell in self.periodic_constraints.owned_cells
            }
            if self.periodic_constraints is not None
            else {}
        )
        result: list[tuple[VariablePCellDofMap, np.ndarray]] = []
        for recovery in self.cell_recovery:
            cell = recovery.cell
            if assembled_trace is not None:
                local_trace = assembled_trace[cell.trace_rows]
            elif self.periodic_constraints is None:
                local_trace = trace[cell.trace_rows]
            else:
                constrained_cell = constrained_by_cell[cell.global_cell]
                local_trace = (
                    constrained_cell.full_trace_from_independent
                    @ trace[constrained_cell.independent_rows]
                )
            interior = (
                self.trace_from_interior_rhs_by_class[
                    recovery.class_key
                ].conj().T
                @ local_trace
            )
            if goal_values is not None:
                interior += _iteratively_refined_lu_solve(
                    self.interior_lu_by_class[recovery.class_key],
                    goal_values[cell.interior_rows],
                    trans=2,
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


def _validate_vector_communicator(
    system: VariablePCondensedTraceSystem,
    vector: PETSc.Vec,
    *,
    role: str,
) -> None:
    expected = system.entity_map.mesh.comm
    actual = vector.comm.tompi4py()
    comparison = MPI.Comm.Compare(expected, actual)
    if comparison not in {MPI.IDENT, MPI.CONGRUENT}:
        raise ValueError(f"{role} uses a different MPI communicator")


def _tensor_sha256(tensor: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(tensor).view(np.uint8)
    ).hexdigest()


def _collective_setup_phase_timings(
    comm: MPI.Intracomm,
    local_seconds: Mapping[str, float],
) -> dict[str, Any]:
    """Return diagnostic wall-time anatomy without changing math state."""

    normalized = {
        str(key): float(value) for key, value in local_seconds.items()
    }
    if any(
        not np.isfinite(value) or value < 0.0
        for value in normalized.values()
    ):
        raise RuntimeError("variable-p setup timing contains an invalid value")
    packets = comm.allgather(normalized)
    keys = tuple(normalized)
    if any(tuple(packet) != keys for packet in packets):
        raise RuntimeError("MPI variable-p timing phase catalogs differ")
    by_rank = {
        key: [float(packet[key]) for packet in packets]
        for key in keys
    }
    return {
        "semantics": (
            "perf_counter wall seconds; by-rank values plus MPI maximum; "
            "overlapping envelopes are named explicitly; diagnostic only"
        ),
        "seconds_by_rank": by_rank,
        "seconds_max": {
            key: max(values) for key, values in by_rank.items()
        },
    }


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
    retain_local_schur_for_research: bool = False,
) -> VariablePCondensedTraceSystem:
    """Project p6 cell tensors, condense interiors, and assemble active rows."""

    function_started = perf_counter()
    input_validation_started = perf_counter()
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
    input_validation_seconds = (
        perf_counter() - input_validation_started
    )
    constraint_validation_started = perf_counter()
    constrained_cells = (
        _validate_trace_constraints(entity_map, constraints)
        if constraints is not None
        else (None,) * len(cells)
    )
    constraint_validation_seconds = (
        perf_counter() - constraint_validation_started
    )

    started = perf_counter()
    graph_setup_started = perf_counter()
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
    graph_setup_seconds = perf_counter() - graph_setup_started
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
    local_preallocation_seconds = (
        perf_counter() - preallocation_started
    )
    preallocation_seconds = float(
        comm.allreduce(
            local_preallocation_seconds,
            op=MPI.MAX,
        )
    )
    matrix_create_started = perf_counter()
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
    matrix_create_seconds = perf_counter() - matrix_create_started

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
    reference_space_seconds = 0.0
    constraint_expansion_seconds = 0.0
    matsetvalues_seconds = 0.0
    recovery_catalog_seconds = 0.0
    interior_recovery_operator_residual = 0.0
    interior_adjoint_operator_residual = 0.0
    cell_loop_started = perf_counter()
    for cell, p6_tensor, raw_key, constrained_cell in zip(
        cells,
        tensors,
        raw_keys,
        constrained_cells,
        strict=True,
    ):
        reference_space_started = perf_counter()
        space = build_variable_p_reference_space(cell.degree_map)
        reference_space_seconds += (
            perf_counter() - reference_space_started
        )
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
            constraint_expansion_started = perf_counter()
            expansion = constrained_cell.full_trace_from_independent
            rows = constrained_cell.independent_rows
            insertion_tensor = (
                expansion.conj().T @ schur @ expansion
            )
            constraint_expansion_seconds += (
                perf_counter() - constraint_expansion_started
            )
        matsetvalues_started = perf_counter()
        matrix.setValues(
            np.asarray(rows, dtype=PETSc.IntType),
            np.asarray(rows, dtype=PETSc.IntType),
            np.asarray(insertion_tensor, dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.ADD_VALUES,
        )
        matsetvalues_seconds += perf_counter() - matsetvalues_started
        insertion_seconds += perf_counter() - insertion_started
        recovery_catalog_started = perf_counter()
        recoveries.append(
            VariablePCellRecovery(
                cell=cell,
                space=space,
                class_key=class_key,
            )
        )
        recovery_catalog_seconds += (
            perf_counter() - recovery_catalog_started
        )
    cell_loop_seconds = perf_counter() - cell_loop_started
    if defer_final_assembly:
        local_assembly_seconds = 0.0
        assembly_seconds = 0.0
        info: dict[str, float] = {}
    else:
        assembly_started = perf_counter()
        matrix.assemble()
        local_assembly_seconds = perf_counter() - assembly_started
        assembly_seconds = float(
            comm.allreduce(
                local_assembly_seconds,
                op=MPI.MAX,
            )
        )
        info = matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
    post_cell_gate_started = perf_counter()
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
    post_cell_gate_seconds = perf_counter() - post_cell_gate_started
    audit_bookkeeping_started = perf_counter()
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
    local_retained_schur_bytes = int(
        sum(value.nbytes for value in schur_cache.values())
    )
    retained_schur: Mapping[tuple[Any, ...], np.ndarray] | None = None
    if retain_local_schur_for_research:
        for value in schur_cache.values():
            value.setflags(write=False)
        retained_schur = MappingProxyType(dict(schur_cache))
    retained_schur_bytes_sum = int(
        comm.allreduce(
            (
                local_retained_schur_bytes
                if retain_local_schur_for_research
                else 0
            ),
            op=MPI.SUM,
        )
    )
    retained_schur_bytes_max = int(
        comm.allreduce(
            (
                local_retained_schur_bytes
                if retain_local_schur_for_research
                else 0
            ),
            op=MPI.MAX,
        )
    )
    retained_schur_class_count_sum = int(
        comm.allreduce(
            len(schur_cache)
            if retain_local_schur_for_research
            else 0,
            op=MPI.SUM,
        )
    )
    audit_bookkeeping_seconds = perf_counter() - audit_bookkeeping_started
    cell_subphase_sum = sum(
        (
            projection_seconds,
            condensation_seconds,
            insertion_seconds,
            reference_space_seconds,
            recovery_catalog_seconds,
        )
    )
    phase_timing = _collective_setup_phase_timings(
        comm,
        {
            "input_tensor_and_mode_validation": input_validation_seconds,
            "trace_constraint_validation": constraint_validation_seconds,
            "active_graph_setup": graph_setup_seconds,
            "exact_preallocation": local_preallocation_seconds,
            "petsc_matrix_create": matrix_create_seconds,
            "cell_loop_total": cell_loop_seconds,
            "reference_space_acquisition": reference_space_seconds,
            "projection_and_orientation": projection_seconds,
            "cell_interior_lu_schur_and_recovery": (
                condensation_seconds
            ),
            "constraint_expansion_ckh_sk_ck": (
                constraint_expansion_seconds
            ),
            "petsc_matsetvalues": matsetvalues_seconds,
            "legacy_insertion_envelope": insertion_seconds,
            "cell_recovery_catalog": recovery_catalog_seconds,
            "cell_loop_unattributed": max(
                0.0,
                cell_loop_seconds - cell_subphase_sum,
            ),
            "final_petsc_assembly": local_assembly_seconds,
            "post_cell_residual_and_structure_gates": (
                post_cell_gate_seconds
            ),
            "audit_and_retention_bookkeeping": (
                audit_bookkeeping_seconds
            ),
            "condensed_builder_total_including_validation": (
                perf_counter() - function_started
            ),
            "legacy_total_build_envelope_after_constraint_validation": (
                perf_counter() - started
            ),
        },
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
        "phase_timing_semantics": phase_timing["semantics"],
        "phase_timings_seconds_by_rank": phase_timing[
            "seconds_by_rank"
        ],
        "phase_timings_seconds_max": phase_timing["seconds_max"],
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
        "retain_local_schur_for_research_requested": bool(
            retain_local_schur_for_research
        ),
        "retained_local_schur_active": bool(
            retain_local_schur_for_research
        ),
        "retained_local_schur_released": False,
        "retained_local_schur_local_class_count": (
            len(schur_cache)
            if retain_local_schur_for_research
            else 0
        ),
        "retained_local_schur_local_bytes": (
            local_retained_schur_bytes
            if retain_local_schur_for_research
            else 0
        ),
        "retained_local_schur_sum_rank_bytes": (
            retained_schur_bytes_sum
        ),
        "retained_local_schur_max_rank_bytes": (
            retained_schur_bytes_max
        ),
        "retained_local_schur_scope": (
            "controlled_live_observer_callback_only"
            if retain_local_schur_for_research
            else "not_retained"
        ),
        "research_local_schur_retention": {
            "enabled": bool(retain_local_schur_for_research),
            "pre_constraint_local_schur": True,
            "readonly": bool(retain_local_schur_for_research),
            "class_count_local": (
                len(schur_cache)
                if retain_local_schur_for_research
                else 0
            ),
            "class_count_sum_across_ranks": (
                retained_schur_class_count_sum
            ),
            "numpy_payload_bytes_local": (
                local_retained_schur_bytes
                if retain_local_schur_for_research
                else 0
            ),
            "numpy_payload_bytes_sum_across_ranks": (
                retained_schur_bytes_sum
            ),
            "numpy_payload_bytes_max_rank": (
                retained_schur_bytes_max
            ),
            "new_array_copy_bytes": 0,
            "includes_Aii": False,
            "includes_Ati": False,
            "includes_Ait": False,
            "ownership": (
                "rank-local classes used by locally owned cells"
            ),
            "lifetime": (
                "builder return through live-observer finally"
                if retain_local_schur_for_research
                else "builder-local only"
            ),
            "rss_pss_uss_semantics": (
                "numpy payload only; not RSS, PSS, USS, allocator "
                "overhead, PETSc matrix, or MUMPS factor"
            ),
            "ordinary_default_changed": False,
        },
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
        retained_local_schur_by_class=retained_schur,
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
    retain_local_schur_for_research: bool = False,
    persistent_raw_tensor_cache_directory: (
        str | os.PathLike[str] | None
    ) = None,
    persistent_raw_tensor_cache_namespace: str | None = None,
) -> VariablePCondensedTraceSystem:
    """Evaluate p6 FFCx tensor classes and assemble the true active system."""

    compiled_builder_started = perf_counter()
    form_validation_started = perf_counter()
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
    form_validation_seconds = perf_counter() - form_validation_started

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
    local_metadata_seconds = perf_counter() - metadata_started
    metadata_seconds = float(
        comm.allreduce(
            local_metadata_seconds,
            op=MPI.MAX,
        )
    )
    raw_cache_started = perf_counter()
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
            persistent_cache_directory=(
                persistent_raw_tensor_cache_directory
            ),
            persistent_cache_namespace=(
                persistent_raw_tensor_cache_namespace
            ),
        )
    )
    raw_cache_seconds = perf_counter() - raw_cache_started
    reduced_builder_started = perf_counter()
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
        retain_local_schur_for_research=(
            retain_local_schur_for_research
        ),
    )
    reduced_builder_seconds = perf_counter() - reduced_builder_started
    compiled_timing = _collective_setup_phase_timings(
        comm,
        {
            "compiled_form_and_element_validation": (
                form_validation_seconds
            ),
            "raw_tensor_class_metadata": local_metadata_seconds,
            "raw_tensor_global_cache_outer_envelope": raw_cache_seconds,
            "condensed_trace_builder_outer_envelope": (
                reduced_builder_seconds
            ),
            "compiled_builder_total_before_audit_publish": (
                perf_counter() - compiled_builder_started
            ),
        },
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
            "compiled_builder_phase_timing_semantics": (
                compiled_timing["semantics"]
            ),
            "compiled_builder_phase_timings_seconds_by_rank": (
                compiled_timing["seconds_by_rank"]
            ),
            "compiled_builder_phase_timings_seconds_max": (
                compiled_timing["seconds_max"]
            ),
            **raw_audit,
        }
    )
    return system


def _global_active_vector_values(
    system: VariablePCondensedTraceSystem,
    vector: PETSc.Vec,
) -> np.ndarray:
    _validate_vector_communicator(
        system,
        vector,
        role="active full vector",
    )
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
    relative_tolerance: float = 0.0,
) -> PETSc.Vec:
    """Apply local Schur and Floquet reductions to an active full vector."""

    comm = system.entity_map.mesh.comm
    preflight_error = None
    try:
        if side not in {"right", "left"}:
            raise ValueError(
                "vector condensation side must be right or left"
            )
        _validate_vector_communicator(
            system,
            active_full_vector,
            role="active full vector",
        )
        if active_full_vector.getSize() != system.entity_map.active_rows:
            raise ValueError(
                "active full vector has the wrong global size"
            )
        if (
            not np.isfinite(float(relative_tolerance))
            or float(relative_tolerance) < 0.0
        ):
            raise ValueError(
                "dual-condensation relative tolerance must be finite "
                "and nonnegative"
            )
    except Exception as exc:
        preflight_error = f"{type(exc).__name__}: {exc}"
    preflight_errors = comm.allgather(preflight_error)
    if any(error is not None for error in preflight_errors):
        raise ValueError(
            "collective distributed dual-condensation preflight failed: "
            + "; ".join(
                f"rank {rank}: {error}"
                for rank, error in enumerate(preflight_errors)
                if error is not None
            )
        )
    owned_values = np.asarray(
        active_full_vector.getArray(readonly=True),
        dtype=np.complex128,
    )
    local_finite = bool(np.all(np.isfinite(owned_values)))
    if not bool(comm.allreduce(local_finite, op=MPI.LAND)):
        raise ValueError("active full vector contains non-finite entries")
    global_maximum = float(
        comm.allreduce(
            float(np.max(np.abs(owned_values), initial=0.0)),
            op=MPI.MAX,
        )
    )
    cutoff = float(relative_tolerance) * global_maximum
    row_start, row_end = map(
        int,
        active_full_vector.getOwnershipRange(),
    )
    constraints = system.trace_constraints
    metadata_error = None
    work_blocks: tuple[Any, ...] = ()
    periodic_by_cell: dict[int, Any] = {}
    block_metadata: list[
        tuple[np.ndarray, np.ndarray, np.ndarray]
    ] = []
    recovery_interior_rows: list[np.ndarray] = []
    raw_coverage_local = np.zeros(
        system.entity_map.active_trace_rows,
        dtype=np.int32,
    )
    independent_coverage_local = np.zeros(
        system.active_trace_rows,
        dtype=np.int32,
    )
    interior_coverage_local = np.zeros(
        (
            system.entity_map.active_rows
            - system.entity_map.active_trace_rows
        ),
        dtype=np.int32,
    )
    try:
        if constraints is None:
            if (
                system.active_trace_rows
                != system.entity_map.active_trace_rows
            ):
                raise ValueError(
                    "unconstrained active/reduced trace rows disagree"
                )
            start = max(row_start, 0)
            stop = min(row_end, system.entity_map.active_trace_rows)
            raw_coverage_local[start:stop] += 1
            independent_coverage_local[start:stop] += 1
        else:
            if (
                int(constraints.independent_trace_rows)
                != system.active_trace_rows
            ):
                raise ValueError(
                    "constraint independent rows disagree with the system"
                )
            routed_blocks = getattr(
                constraints,
                "work_owned_entity_blocks",
                None,
            )
            work_blocks = (
                tuple(routed_blocks)
                if routed_blocks is not None
                else tuple(
                    block
                    for block in constraints.entity_blocks.values()
                    if row_start <= int(block.full_rows[0]) < row_end
                )
            )
            for block in work_blocks:
                full_rows = np.asarray(block.full_rows, dtype=np.int64)
                independent_rows = np.asarray(
                    block.independent_rows,
                    dtype=np.int64,
                )
                expansion = np.asarray(
                    block.full_from_independent,
                    dtype=np.complex128,
                )
                if (
                    full_rows.ndim != 1
                    or independent_rows.ndim != 1
                    or len(full_rows) == 0
                    or len(independent_rows) == 0
                    or len(np.unique(full_rows)) != len(full_rows)
                    or len(np.unique(independent_rows))
                    != len(independent_rows)
                    or np.any(full_rows < 0)
                    or np.any(
                        full_rows
                        >= system.entity_map.active_trace_rows
                    )
                    or np.any(independent_rows < 0)
                    or np.any(
                        independent_rows >= system.active_trace_rows
                    )
                    or expansion.shape
                    != (len(full_rows), len(independent_rows))
                    or not np.all(np.isfinite(expansion))
                ):
                    raise ValueError(
                        "one dual-condensation constraint block is invalid"
                    )
                if routed_blocks is not None and (
                    int(block.active_vector_work_owner_rank) != comm.rank
                    or not (
                        row_start <= int(full_rows[0]) < row_end
                    )
                ):
                    raise RuntimeError(
                        "owner-routed dual-condensation block reached the "
                        "wrong active-vector work owner"
                    )
                raw_coverage_local[full_rows] += 1
                independent_coverage_local[independent_rows] += 1
                block_metadata.append(
                    (full_rows, independent_rows, expansion)
                )
            periodic_by_cell = {
                int(cell.global_cell): cell
                for cell in constraints.owned_cells
            }
        for recovery in system.cell_recovery:
            interior_rows = np.asarray(
                recovery.cell.interior_rows,
                dtype=np.int64,
            )
            if (
                interior_rows.ndim != 1
                or len(np.unique(interior_rows)) != len(interior_rows)
                or np.any(
                    interior_rows < system.entity_map.active_trace_rows
                )
                or np.any(
                    interior_rows >= system.entity_map.active_rows
                )
            ):
                raise ValueError(
                    "one dual-condensation cell has invalid interior rows"
                )
            interior_coverage_local[
                interior_rows
                - system.entity_map.active_trace_rows
            ] += 1
            if constraints is not None:
                constrained_cell = periodic_by_cell.get(
                    int(recovery.cell.global_cell)
                )
                if constrained_cell is None:
                    raise RuntimeError(
                        "one dual-condensation cell lacks a constraint map"
                    )
            recovery_interior_rows.append(interior_rows)
    except Exception as exc:
        metadata_error = f"{type(exc).__name__}: {exc}"
    metadata_errors = comm.allgather(metadata_error)
    if any(error is not None for error in metadata_errors):
        raise ValueError(
            "collective distributed dual-condensation metadata failed: "
            + "; ".join(
                f"rank {rank}: {error}"
                for rank, error in enumerate(metadata_errors)
                if error is not None
            )
        )

    raw_coverage = np.empty_like(raw_coverage_local)
    independent_coverage = np.empty_like(independent_coverage_local)
    interior_coverage = np.empty_like(interior_coverage_local)
    comm.Allreduce(raw_coverage_local, raw_coverage, op=MPI.SUM)
    comm.Allreduce(
        independent_coverage_local,
        independent_coverage,
        op=MPI.SUM,
    )
    comm.Allreduce(
        interior_coverage_local,
        interior_coverage,
        op=MPI.SUM,
    )
    if (
        not np.all(raw_coverage == 1)
        or not np.all(independent_coverage >= 1)
        or not np.all(interior_coverage == 1)
    ):
        raise RuntimeError(
            "distributed dual-condensation constraint blocks do not cover "
            "each raw/interior row exactly once and every independent row "
            "at least once"
        )

    requested_rows = np.concatenate(
        [
            *[metadata[0] for metadata in block_metadata],
            *recovery_interior_rows,
        ]
        or [np.empty(0, dtype=np.int64)]
    )
    pending_base: list[tuple[np.ndarray, np.ndarray]] = []
    pending_corrections: list[tuple[np.ndarray, np.ndarray]] = []
    computation_error = None
    with PETScSelectedRowLayout.create(
        active_full_vector,
        requested_rows,
    ) as selected_layout:
        selected_values = selected_layout.gather(active_full_vector)
        selected_audit = dict(selected_layout.audit)
        try:
            if constraints is None:
                start = max(row_start, 0)
                stop = min(row_end, system.entity_map.active_trace_rows)
                if stop > start:
                    rows = np.arange(start, stop, dtype=np.int64)
                    local_start = start - row_start
                    values = np.asarray(
                        owned_values[
                            local_start : local_start + len(rows)
                        ],
                        dtype=np.complex128,
                    )
                    retained = np.abs(values) > cutoff
                    pending_base.append(
                        (rows[retained], values[retained].copy())
                    )
            else:
                for full_rows, independent_rows, expansion in block_metadata:
                    projected = (
                        expansion.conj().T
                        @ selected_values[
                            selected_layout.positions(full_rows)
                        ]
                    )
                    retained = np.abs(projected) > cutoff
                    pending_base.append(
                        (
                            independent_rows[retained],
                            projected[retained].copy(),
                        )
                    )

            for recovery, interior_rows in zip(
                system.cell_recovery,
                recovery_interior_rows,
                strict=True,
            ):
                interior_values = selected_values[
                    selected_layout.positions(interior_rows)
                ]
                if (
                    float(
                        np.max(
                            np.abs(interior_values),
                            initial=0.0,
                        )
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
                if constraints is None:
                    rows = np.asarray(
                        recovery.cell.trace_rows,
                        dtype=np.int64,
                    )
                else:
                    constrained_cell = periodic_by_cell[
                        int(recovery.cell.global_cell)
                    ]
                    correction = (
                        np.asarray(
                            constrained_cell.full_trace_from_independent,
                            dtype=np.complex128,
                        ).conj().T
                        @ correction
                    )
                    rows = np.asarray(
                        constrained_cell.independent_rows,
                        dtype=np.int64,
                    )
                retained = np.abs(correction) > cutoff
                pending_corrections.append(
                    (
                        rows[retained],
                        correction[retained].copy(),
                    )
                )
        except Exception as exc:
            computation_error = f"{type(exc).__name__}: {exc}"
    computation_errors = comm.allgather(computation_error)
    if any(error is not None for error in computation_errors):
        raise RuntimeError(
            "collective distributed dual condensation failed: "
            + "; ".join(
                f"rank {rank}: {error}"
                for rank, error in enumerate(computation_errors)
                if error is not None
            )
        )

    target = system.matrix.createVecRight()
    insertion_error = None
    try:
        target.set(PETSc.ScalarType(0.0))
        for rows, values in (*pending_base, *pending_corrections):
            if not len(rows):
                continue
            target.setValues(
                np.asarray(rows, dtype=PETSc.IntType),
                np.asarray(values, dtype=PETSc.ScalarType),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
    except Exception as exc:
        insertion_error = f"{type(exc).__name__}: {exc}"
    insertion_errors = comm.allgather(insertion_error)
    if any(error is not None for error in insertion_errors):
        target.destroy()
        raise RuntimeError(
            "collective distributed dual-condensation insertion failed: "
            + "; ".join(
                f"rank {rank}: {error}"
                for rank, error in enumerate(insertion_errors)
                if error is not None
            )
        )
    try:
        target.assemble()
    except Exception:
        target.destroy()
        raise

    audit = {
        "schema_version": (
            "task035e.distributed-active-dual-condensation.v1"
        ),
        "status": "selected_row_dual_condensation_pass",
        "pass": True,
        "side": side,
        "input_active_rows": system.entity_map.active_rows,
        "raw_trace_rows": system.entity_map.active_trace_rows,
        "independent_trace_rows": system.active_trace_rows,
        "constraint_mode": (
            "unconstrained_direct_owned_trace"
            if constraints is None
            else (
                "owner_routed_entity_blocks"
                if getattr(
                    constraints,
                    "work_owned_entity_blocks",
                    None,
                )
                is not None
                else "legacy_replicated_entity_blocks_owner_filtered"
            )
        ),
        "global_input_max_abs": global_maximum,
        "relative_tolerance": float(relative_tolerance),
        "absolute_cutoff": cutoff,
        "constraint_block_count_global": int(
            comm.allreduce(len(block_metadata), op=MPI.SUM)
        ),
        "owned_cell_correction_count_local": len(
            recovery_interior_rows
        ),
        "base_contribution_count_local": len(pending_base),
        "interior_correction_count_local": len(
            pending_corrections
        ),
        "raw_trace_row_coverage_min": int(raw_coverage.min()),
        "raw_trace_row_coverage_max": int(raw_coverage.max()),
        "independent_row_coverage_min": int(
            independent_coverage.min()
        ),
        "independent_row_coverage_max": int(
            independent_coverage.max()
        ),
        "interior_row_coverage_min": int(
            interior_coverage.min(initial=1)
        ),
        "interior_row_coverage_max": int(
            interior_coverage.max(initial=1)
        ),
        "raw_trace_rows_exactly_once": True,
        "active_interior_rows_exactly_once": True,
        "constraint_blocks_processed_exactly_once": True,
        "independent_rows_covered": True,
        "independent_row_block_multiplicity_preserved": True,
        "independent_rows_unique_within_each_block": True,
        "overlapping_independent_rows_accumulated_with_add": True,
        "base_trace_insert_mode": "ADD_VALUES",
        "cell_interior_correction_insert_mode": "ADD_VALUES",
        "active_selected_rows": selected_audit,
        "replicated_active_full_vector_bytes_per_rank": 0,
        "python_full_vector_allgather_used": False,
        "default_exact_zero_only_filter": (
            float(relative_tolerance) == 0.0
        ),
        "python_collectives_contain_metadata_or_scalar_audits_only": True,
        "ordinary_default_changed": False,
    }
    call_count = int(
        system.build_audit.get(
            "active_dual_condensation_call_count",
            0,
        )
    ) + 1
    system.build_audit["active_dual_condensation_call_count"] = call_count
    system.build_audit["last_active_dual_condensation"] = audit
    return target


def extract_variable_p_active_primal_to_reduced(
    system: VariablePCondensedTraceSystem,
    active_full_primal: PETSc.Vec,
    *,
    auxiliary_reduced_values: np.ndarray,
    roundtrip_tolerance: float = 5.0e-10,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Extract a conforming primal trace without dual/Schur condensation.

    ``condense_variable_p_active_vector_to_trace`` transforms a dual vector
    and therefore applies conjugate-transpose constraint and interior-Schur
    actions.  A recovered primal field needs the inverse operation on its
    trace: for each physical entity block solve ``C q = u_full`` and place
    ``q`` directly in the independent reduced coordinates.
    """

    _validate_vector_communicator(
        system,
        active_full_primal,
        role="active full primal vector",
    )
    if active_full_primal.getSize() != system.entity_map.active_rows:
        raise ValueError("active full primal vector has the wrong global size")
    if (
        not np.isfinite(float(roundtrip_tolerance))
        or float(roundtrip_tolerance) <= 0.0
    ):
        raise ValueError("primal trace round-trip tolerance must be positive")
    comm = system.entity_map.mesh.comm
    structural_error = None
    try:
        constraints = system.trace_constraints
        if (
            system.entity_map.active_rows
            < system.entity_map.active_trace_rows
            or system.entity_map.active_trace_rows <= 0
            or system.active_trace_rows <= 0
            or system.appended_rows < 0
        ):
            raise ValueError(
                "primal trace extraction system row counts are invalid"
            )
        if constraints is None:
            if (
                system.active_trace_rows
                != system.entity_map.active_trace_rows
            ):
                raise ValueError(
                    "unconstrained primal trace row counts do not match"
                )
        elif (
            int(constraints.independent_trace_rows)
            != system.active_trace_rows
        ):
            raise ValueError(
                "constraint independent-row count does not match the system"
            )
    except (AttributeError, TypeError, ValueError) as exc:
        constraints = None
        structural_error = f"{type(exc).__name__}: {exc}"
    structural_packets = comm.allgather(
        (structural_error, float(roundtrip_tolerance))
    )
    structural_failures = [
        f"rank {rank}: {error}"
        for rank, (error, _tolerance) in enumerate(structural_packets)
        if error is not None
    ]
    tolerances = {
        tolerance
        for error, tolerance in structural_packets
        if error is None
    }
    if structural_failures or len(tolerances) != 1:
        detail = (
            structural_failures
            if structural_failures
            else ["MPI ranks supplied different round-trip tolerances"]
        )
        raise ValueError(
            "collective primal trace system validation failed: "
            + "; ".join(detail)
        )
    local_active = np.asarray(
        active_full_primal.getArray(readonly=True),
        dtype=np.complex128,
    )
    local_finite = bool(np.all(np.isfinite(local_active)))
    if not bool(comm.allreduce(local_finite, op=MPI.LAND)):
        raise ValueError("active full primal vector contains non-finite values")

    auxiliary_error = None
    auxiliary = np.empty(0, dtype=np.complex128)
    try:
        supplied_auxiliary = np.asarray(auxiliary_reduced_values)
        if supplied_auxiliary.ndim != 1:
            raise ValueError(
                "auxiliary reduced values must be one-dimensional"
            )
        auxiliary = np.asarray(
            supplied_auxiliary,
            dtype=np.complex128,
        )
        if auxiliary.shape != (system.appended_rows,):
            raise ValueError(
                "auxiliary reduced value count must equal appended_rows"
            )
        if not np.all(np.isfinite(auxiliary)):
            raise ValueError(
                "auxiliary reduced values contain non-finite entries"
            )
    except (TypeError, ValueError) as exc:
        auxiliary_error = f"{type(exc).__name__}: {exc}"
    auxiliary_packets = comm.allgather(
        (
            auxiliary_error,
            (
                None
                if auxiliary_error is not None
                else hashlib.sha256(
                    np.ascontiguousarray(auxiliary).view(np.uint8)
                ).hexdigest()
            ),
        )
    )
    auxiliary_failures = [
        f"rank {rank}: {error}"
        for rank, (error, _sha256) in enumerate(auxiliary_packets)
        if error is not None
    ]
    auxiliary_hashes = {
        sha256
        for error, sha256 in auxiliary_packets
        if error is None
    }
    if auxiliary_failures or len(auxiliary_hashes) != 1:
        detail = (
            auxiliary_failures
            if auxiliary_failures
            else ["MPI ranks supplied different auxiliary reduced values"]
        )
        raise ValueError(
            "collective auxiliary primal-trace validation failed: "
            + "; ".join(detail)
        )

    input_start, input_end = map(
        int,
        active_full_primal.getOwnershipRange(),
    )
    block_error = None
    blocks: tuple[Any, ...] = ()
    block_metadata: list[
        tuple[Any, np.ndarray, np.ndarray, np.ndarray]
    ] = []
    try:
        if constraints is not None:
            routed_blocks = getattr(
                constraints,
                "work_owned_entity_blocks",
                None,
            )
            blocks = (
                tuple(routed_blocks)
                if routed_blocks is not None
                else tuple(
                    block
                    for block in constraints.entity_blocks.values()
                    if input_start <= int(block.full_rows[0]) < input_end
                )
            )
            for block in blocks:
                full_rows = np.asarray(block.full_rows, dtype=np.int64)
                independent_rows = np.asarray(
                    block.independent_rows,
                    dtype=np.int64,
                )
                expansion = np.asarray(
                    block.full_from_independent,
                    dtype=np.complex128,
                )
                if (
                    full_rows.ndim != 1
                    or independent_rows.ndim != 1
                    or len(full_rows) == 0
                    or len(independent_rows) == 0
                    or len(np.unique(full_rows)) != len(full_rows)
                    or len(np.unique(independent_rows))
                    != len(independent_rows)
                    or np.any(full_rows < 0)
                    or np.any(
                        full_rows
                        >= system.entity_map.active_trace_rows
                    )
                    or np.any(independent_rows < 0)
                    or np.any(
                        independent_rows >= system.active_trace_rows
                    )
                ):
                    raise ValueError(
                        "one primal trace block has invalid row identities"
                    )
                if expansion.shape != (
                    len(full_rows),
                    len(independent_rows),
                ):
                    raise ValueError(
                        "one primal trace block expansion has the wrong shape"
                    )
                if not np.all(np.isfinite(expansion)):
                    raise ValueError(
                        "one primal trace block expansion is non-finite"
                    )
                if routed_blocks is not None:
                    if (
                        int(block.active_vector_work_owner_rank)
                        != comm.rank
                        or not (
                            input_start
                            <= int(full_rows[0])
                            < input_end
                        )
                    ):
                        raise RuntimeError(
                            "owner-routed primal trace block reached the "
                            "wrong active-vector work owner"
                        )
                block_metadata.append(
                    (block, full_rows, independent_rows, expansion)
                )
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        block_error = f"{type(exc).__name__}: {exc}"
    block_errors = comm.allgather(block_error)
    if any(error is not None for error in block_errors):
        raise ValueError(
            "collective primal trace block validation failed: "
            + "; ".join(
                f"rank {rank}: {error}"
                for rank, error in enumerate(block_errors)
                if error is not None
            )
        )

    raw_coverage_local = np.zeros(
        system.entity_map.active_trace_rows,
        dtype=np.int32,
    )
    independent_coverage_local = np.zeros(
        system.active_trace_rows,
        dtype=np.int32,
    )
    pending_values: list[tuple[np.ndarray, np.ndarray]] = []
    local_error_sq = 0.0
    local_reference_sq = 0.0
    local_maximum_error = 0.0
    local_maximum_relative = 0.0
    local_maximum_condition = 0.0
    local_minimum_singular = np.inf
    local_left_inverse_count = 0
    selected_audit: dict[str, Any]
    solve_error = None
    if constraints is None:
        start = max(input_start, 0)
        stop = min(input_end, system.entity_map.active_trace_rows)
        rows = np.arange(start, stop, dtype=np.int64)
        offset = start - input_start
        values = np.asarray(
            local_active[offset : offset + len(rows)],
            dtype=np.complex128,
        ).copy()
        raw_coverage_local[rows] += 1
        independent_coverage_local[rows] += 1
        pending_values.append((rows, values))
        selected_audit = {
            "schema_version": "task035e.petsc-selected-row-layout.v1",
            "status": "direct_owned_trace_slice",
            "pass": True,
            "global_vector_rows": system.entity_map.active_rows,
            "requested_row_count_local": len(rows),
            "selected_unique_row_count_local": len(rows),
            "duplicate_request_count_local": 0,
            "selected_value_bytes_local": int(values.nbytes),
            "replicated_full_vector_bytes_per_rank": 0,
            "full_vector_allgather_used": False,
            "petsc_is_scatter_used": False,
        }
    else:
        requested_rows = np.concatenate(
            [metadata[1] for metadata in block_metadata]
            or [np.empty(0, dtype=np.int64)]
        )
        with PETScSelectedRowLayout.create(
            active_full_primal,
            requested_rows,
        ) as layout:
            selected_values = layout.gather(active_full_primal)
            selected_audit = dict(layout.audit)
            try:
                for (
                    _block,
                    full_rows,
                    independent_rows,
                    expansion,
                ) in block_metadata:
                    full_values = selected_values[
                        layout.positions(full_rows)
                    ]
                    solution, _residuals, rank, singular_values = (
                        np.linalg.lstsq(
                            expansion,
                            full_values,
                            rcond=None,
                        )
                    )
                    if int(rank) != len(independent_rows):
                        raise RuntimeError(
                            "one primal trace block left inverse is rank "
                            "deficient"
                        )
                    solution = np.asarray(
                        solution,
                        dtype=np.complex128,
                    )
                    if not np.all(np.isfinite(solution)):
                        raise RuntimeError(
                            "one primal trace block left inverse is non-finite"
                        )
                    roundtrip = expansion @ solution
                    error = roundtrip - full_values
                    error_norm = float(np.linalg.norm(error))
                    reference_norm = float(np.linalg.norm(full_values))
                    relative = (
                        error_norm
                        / max(reference_norm, np.finfo(np.float64).tiny)
                    )
                    maximum_error = float(
                        np.max(np.abs(error), initial=0.0)
                    )
                    if relative > float(roundtrip_tolerance):
                        raise RuntimeError(
                            "one primal trace block is not conforming: "
                            f"relative round-trip={relative:.6e}"
                        )
                    singular_values = np.asarray(
                        singular_values,
                        dtype=np.float64,
                    )
                    minimum_singular = float(
                        np.min(singular_values, initial=np.inf)
                    )
                    maximum_singular = float(
                        np.max(singular_values, initial=0.0)
                    )
                    condition = (
                        maximum_singular / minimum_singular
                        if minimum_singular > 0.0
                        else np.inf
                    )
                    raw_coverage_local[full_rows] += 1
                    independent_coverage_local[independent_rows] += 1
                    pending_values.append(
                        (independent_rows, solution.copy())
                    )
                    local_error_sq += error_norm**2
                    local_reference_sq += reference_norm**2
                    local_maximum_error = max(
                        local_maximum_error,
                        maximum_error,
                    )
                    local_maximum_relative = max(
                        local_maximum_relative,
                        relative,
                    )
                    local_maximum_condition = max(
                        local_maximum_condition,
                        condition,
                    )
                    local_minimum_singular = min(
                        local_minimum_singular,
                        minimum_singular,
                    )
                    local_left_inverse_count += 1
            except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                solve_error = f"{type(exc).__name__}: {exc}"
    solve_errors = comm.allgather(solve_error)
    if any(error is not None for error in solve_errors):
        raise RuntimeError(
            "collective conforming primal trace extraction failed: "
            + "; ".join(
                f"rank {rank}: {error}"
                for rank, error in enumerate(solve_errors)
                if error is not None
            )
        )

    raw_coverage = np.empty_like(raw_coverage_local)
    independent_coverage = np.empty_like(independent_coverage_local)
    comm.Allreduce(raw_coverage_local, raw_coverage, op=MPI.SUM)
    comm.Allreduce(
        independent_coverage_local,
        independent_coverage,
        op=MPI.SUM,
    )
    raw_exact = bool(np.all(raw_coverage == 1))
    independent_exact = bool(np.all(independent_coverage == 1))
    coverage_packets = comm.allgather((raw_exact, independent_exact))
    if not all(raw and independent for raw, independent in coverage_packets):
        raise RuntimeError(
            "primal trace extraction coverage is not exactly once: "
            f"raw_minmax=({int(raw_coverage.min())},"
            f"{int(raw_coverage.max())}), "
            "independent_minmax="
            f"({int(independent_coverage.min())},"
            f"{int(independent_coverage.max())})"
        )

    target = system.matrix.createVecRight()
    try:
        expected_reduced_rows = (
            system.active_trace_rows + system.appended_rows
        )
        if target.getSize() != expected_reduced_rows:
            raise RuntimeError(
                "reduced matrix vector size does not match trace+auxiliary rows"
            )
        target.set(PETSc.ScalarType(0.0))
        for rows, values in pending_values:
            target.setValues(
                np.asarray(rows, dtype=PETSc.IntType),
                np.asarray(values, dtype=PETSc.ScalarType),
                addv=PETSc.InsertMode.INSERT_VALUES,
            )
        target_start, target_end = map(int, target.getOwnershipRange())
        auxiliary_start = system.active_trace_rows
        local_auxiliary_start = max(target_start, auxiliary_start)
        local_auxiliary_end = min(
            target_end,
            auxiliary_start + system.appended_rows,
        )
        if local_auxiliary_end > local_auxiliary_start:
            auxiliary_positions = np.arange(
                local_auxiliary_start,
                local_auxiliary_end,
                dtype=np.int64,
            )
            target.setValues(
                np.asarray(
                    auxiliary_positions,
                    dtype=PETSc.IntType,
                ),
                np.asarray(
                    auxiliary[
                        auxiliary_positions - auxiliary_start
                    ],
                    dtype=PETSc.ScalarType,
                ),
                addv=PETSc.InsertMode.INSERT_VALUES,
            )
        target.assemble()
    except Exception:
        target.destroy()
        raise

    global_error_norm = float(
        np.sqrt(comm.allreduce(local_error_sq, op=MPI.SUM))
    )
    global_reference_norm = float(
        np.sqrt(comm.allreduce(local_reference_sq, op=MPI.SUM))
    )
    global_relative = (
        global_error_norm
        / max(global_reference_norm, np.finfo(np.float64).tiny)
        if constraints is not None
        else 0.0
    )
    audit = {
        "schema_version": (
            "task035e.active-full-primal-to-independent-trace.v1"
        ),
        "status": "conforming_primal_trace_extracted",
        "pass": True,
        "input_active_full_rows": system.entity_map.active_rows,
        "raw_active_trace_rows": (
            system.entity_map.active_trace_rows
        ),
        "independent_trace_rows": system.active_trace_rows,
        "appended_auxiliary_rows": system.appended_rows,
        "output_reduced_rows": int(target.getSize()),
        "constraint_mode": (
            "direct_owned_trace"
            if constraints is None
            else (
                "owner_routed_entity_blocks"
                if getattr(
                    constraints,
                    "work_owned_entity_blocks",
                    None,
                )
                is not None
                else "legacy_replicated_entity_blocks_owner_filtered"
            )
        ),
        "left_inverse_method": (
            "not_required"
            if constraints is None
            else "numpy_lstsq_svd_rank_checked"
        ),
        "left_inverse_block_count_global": int(
            comm.allreduce(local_left_inverse_count, op=MPI.SUM)
        ),
        "maximum_block_roundtrip_relative_l2": float(
            comm.allreduce(local_maximum_relative, op=MPI.MAX)
        ),
        "global_roundtrip_relative_l2": global_relative,
        "maximum_roundtrip_abs_error": float(
            comm.allreduce(local_maximum_error, op=MPI.MAX)
        ),
        "roundtrip_tolerance": float(roundtrip_tolerance),
        "maximum_left_inverse_condition": float(
            comm.allreduce(local_maximum_condition, op=MPI.MAX)
        ),
        "minimum_left_inverse_singular_value": (
            None
            if constraints is None
            else float(
                comm.allreduce(local_minimum_singular, op=MPI.MIN)
            )
        ),
        "raw_trace_row_coverage_min": int(raw_coverage.min()),
        "raw_trace_row_coverage_max": int(raw_coverage.max()),
        "independent_row_coverage_min": int(
            independent_coverage.min()
        ),
        "independent_row_coverage_max": int(
            independent_coverage.max()
        ),
        "raw_trace_rows_exactly_once": raw_exact,
        "independent_rows_exactly_once": independent_exact,
        "independent_row_values_consistent": independent_exact,
        "active_selected_rows": selected_audit,
        "auxiliary_values_explicit": True,
        "auxiliary_value_count": len(auxiliary),
        "auxiliary_values_identical_across_mpi": True,
        "mpi_ownership_fail_closed": True,
        "replicated_active_full_vector_bytes_per_rank": 0,
        "full_vector_allgather_used": False,
        "python_collectives_contain_metadata_or_scalar_audits_only": True,
        "ordinary_default_changed": False,
    }
    if (
        audit["maximum_block_roundtrip_relative_l2"]
        > float(roundtrip_tolerance)
        or audit["global_roundtrip_relative_l2"]
        > float(roundtrip_tolerance)
    ):
        target.destroy()
        raise RuntimeError(
            "primal trace extraction global round-trip gate failed"
        )
    return target, audit


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


def _global_reduced_trace_values(
    system: VariablePCondensedTraceSystem,
    trace_values: PETSc.Vec | np.ndarray,
) -> np.ndarray:
    """Gather and validate the trace part of one reduced vector."""

    if isinstance(trace_values, PETSc.Vec):
        _validate_vector_communicator(
            system,
            trace_values,
            role="reduced trace vector",
        )
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
    if not np.all(np.isfinite(trace)):
        raise ValueError("reduced trace vector contains non-finite entries")
    return np.ascontiguousarray(trace)


def retained_variable_p_owned_cell_schur_actions(
    system: VariablePCondensedTraceSystem,
    *,
    reduced_trace_values: PETSc.Vec | np.ndarray | None = None,
    local_trace_values_by_global_cell: (
        Mapping[int, np.ndarray] | None
    ) = None,
) -> tuple[
    tuple[VariablePOwnedCellSchurAction, ...],
    dict[str, Any],
]:
    """Apply retained pre-constraint Schur classes on owned cells.

    Exactly one trace source is required.  A reduced vector is expanded
    through the qualified Floquet/hanging map.  A per-global-cell mapping is
    intended for a separately hash-qualified same-trace snapshot.
    """

    retained = system.retained_local_schur_by_class
    if retained is None:
        raise RuntimeError(
            "local Schur actions require explicit research retention"
        )
    if (reduced_trace_values is None) == (
        local_trace_values_by_global_cell is None
    ):
        raise ValueError(
            "supply exactly one reduced or per-cell local trace source"
        )
    expected_keys = {
        recovery.class_key for recovery in system.cell_recovery
    }
    if set(retained) != expected_keys:
        raise RuntimeError(
            "retained local Schur classes do not match owned recovery cells"
        )

    reduced_trace = (
        None
        if reduced_trace_values is None
        else _global_reduced_trace_values(
            system,
            reduced_trace_values,
        )
    )
    constrained_by_cell = (
        {}
        if system.trace_constraints is None
        else {
            int(cell.global_cell): cell
            for cell in system.trace_constraints.owned_cells
        }
    )
    actions: list[VariablePOwnedCellSchurAction] = []
    local_action_bytes = 0
    for recovery in system.cell_recovery:
        cell = recovery.cell
        if reduced_trace is not None:
            if system.trace_constraints is None:
                local_trace = reduced_trace[cell.trace_rows].copy()
            else:
                constrained = constrained_by_cell[cell.global_cell]
                local_trace = np.asarray(
                    constrained.full_trace_from_independent
                    @ reduced_trace[constrained.independent_rows],
                    dtype=np.complex128,
                )
        else:
            raw = local_trace_values_by_global_cell.get(
                cell.global_cell
            )
            if raw is None:
                raise ValueError(
                    "per-cell trace snapshot is missing owned global cell "
                    f"{cell.global_cell}"
                )
            local_trace = np.asarray(
                raw,
                dtype=np.complex128,
            ).copy()
        expected_shape = (len(cell.trace_rows),)
        if local_trace.shape != expected_shape:
            raise ValueError(
                "local trace snapshot has the wrong shape for global cell "
                f"{cell.global_cell}: {local_trace.shape} != "
                f"{expected_shape}"
            )
        if not np.all(np.isfinite(local_trace)):
            raise ValueError("local trace snapshot contains non-finite values")
        schur = retained[recovery.class_key]
        if schur.shape != (
            len(cell.trace_rows),
            len(cell.trace_rows),
        ):
            raise RuntimeError(
                "retained local Schur shape does not match its cell trace"
            )
        action = np.ascontiguousarray(schur @ local_trace)
        if not np.all(np.isfinite(action)):
            raise RuntimeError(
                "retained local Schur action contains non-finite values"
            )
        trace_rows = np.asarray(cell.trace_rows, dtype=np.int64).copy()
        for values in (trace_rows, local_trace, action):
            values.setflags(write=False)
        local_action_bytes += int(
            trace_rows.nbytes + local_trace.nbytes + action.nbytes
        )
        actions.append(
            VariablePOwnedCellSchurAction(
                local_cell=int(cell.local_cell),
                global_cell=int(cell.global_cell),
                cell_info=int(cell.cell_info),
                degree_signature=str(cell.degree_map.signature),
                trace_rows=trace_rows,
                local_trace_values=local_trace,
                local_condensed_action=action,
            )
        )
    comm = system.entity_map.mesh.comm
    global_cell_count = int(
        comm.allreduce(len(actions), op=MPI.SUM)
    )
    return tuple(actions), {
        "schema_version": (
            "task035d.variable-p-owned-cell-schur-actions.v1"
        ),
        "status": "owned_cell_schur_actions_evaluated",
        "pass": True,
        "trace_source": (
            "qualified_reduced_trace_constraint_expansion"
            if reduced_trace is not None
            else "hash_qualified_per_global_cell_snapshot"
        ),
        "owned_cell_count_local": len(actions),
        "owned_cell_count_global": global_cell_count,
        "action_payload_bytes_local": local_action_bytes,
        "schur_payload_gathered_across_ranks": False,
        "cell_owner_computes_local_action": True,
        "ordinary_default_changed": False,
    }


def _expand_variable_p_reduced_trace(
    system: VariablePCondensedTraceSystem,
    trace: np.ndarray,
) -> tuple[PETSc.Vec, np.ndarray]:
    """Expand one independent trace into all raw active trace rows."""

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
    return recovered, assembled_active_trace


def recover_variable_p_active_full_vector(
    system: VariablePCondensedTraceSystem,
    trace_values: PETSc.Vec | np.ndarray,
    *,
    active_full_rhs: PETSc.Vec | None = None,
) -> PETSc.Vec:
    """Recover the conforming full active primal coefficient vector."""

    trace = _global_reduced_trace_values(system, trace_values)
    recovered, assembled_active_trace = (
        _expand_variable_p_reduced_trace(system, trace)
    )
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


def recover_variable_p_active_full_adjoint_vector(
    system: VariablePCondensedTraceSystem,
    trace_values: PETSc.Vec | np.ndarray,
    *,
    active_full_goal: PETSc.Vec | None = None,
) -> PETSc.Vec:
    """Recover the exact active adjoint after trace/interior elimination.

    If ``z_t`` is the raw trace adjoint and ``g_i`` is the optional
    cell-interior goal block, every owned cell is recovered as

    ``z_i = -A_ii^{-H} A_ti^H z_t + A_ii^{-H} g_i``.

    This is intentionally separate from primal recovery: using the primal
    ``-A_ii^{-1} A_it`` map is wrong for complex non-Hermitian Maxwell
    operators.
    """

    trace = _global_reduced_trace_values(system, trace_values)
    recovered, assembled_active_trace = (
        _expand_variable_p_reduced_trace(system, trace)
    )
    for cell, local_active in system.recover_owned_active_adjoint_cells(
        trace,
        active_full_goal=active_full_goal,
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


def audit_variable_p_active_full_adjoint_recovery(
    system: VariablePCondensedTraceSystem,
    active_full_adjoint: PETSc.Vec,
    *,
    active_full_goal: PETSc.Vec | None = None,
    relative_tolerance: float = 5.0e-11,
    absolute_tolerance: float = 5.0e-9,
) -> dict[str, Any]:
    """Audit every eliminated equation of one recovered active adjoint."""

    adjoint = _global_active_vector_values(system, active_full_adjoint)
    goal = (
        np.zeros(system.entity_map.active_rows, dtype=np.complex128)
        if active_full_goal is None
        else _global_active_vector_values(system, active_full_goal)
    )
    local_residual_sq = 0.0
    local_reference_sq = 0.0
    local_maximum = 0.0
    local_equations = 0
    for recovery in system.cell_recovery:
        cell = recovery.cell
        factor = system.interior_lu_by_class[recovery.class_key]
        trace = adjoint[cell.trace_rows]
        interior = adjoint[cell.interior_rows]
        interior_goal = goal[cell.interior_rows]
        adjoint_trace_lift = (
            -system.trace_from_interior_rhs_by_class[
                recovery.class_key
            ].conj().T
            @ trace
        )
        interior_action = _lu_factor_matrix_action(
            factor,
            interior,
            trans=2,
        )
        coupling_action = _lu_factor_matrix_action(
            factor,
            adjoint_trace_lift,
            trans=2,
        )
        residual = (
            interior_action + coupling_action - interior_goal
        )
        local_residual_sq += float(np.vdot(residual, residual).real)
        local_reference_sq += float(
            np.vdot(interior_action, interior_action).real
            + np.vdot(coupling_action, coupling_action).real
            + np.vdot(interior_goal, interior_goal).real
        )
        local_maximum = max(
            local_maximum,
            float(np.max(np.abs(residual), initial=0.0)),
        )
        local_equations += len(cell.interior_rows)
    comm = system.entity_map.mesh.comm
    residual_norm = float(
        np.sqrt(comm.allreduce(local_residual_sq, op=MPI.SUM))
    )
    reference_norm = float(
        np.sqrt(comm.allreduce(local_reference_sq, op=MPI.SUM))
    )
    maximum = float(comm.allreduce(local_maximum, op=MPI.MAX))
    equations = int(comm.allreduce(local_equations, op=MPI.SUM))
    relative = residual_norm / max(reference_norm, 1.0)
    passed = (
        equations
        == system.entity_map.active_rows
        - system.entity_map.active_trace_rows
        and relative <= float(relative_tolerance)
        and maximum <= float(absolute_tolerance)
    )
    audit = {
        "schema_version": (
            "task035d.variable-p-active-adjoint-recovery.v1"
        ),
        "status": (
            "variable_p_active_adjoint_recovery_pass"
            if passed
            else "variable_p_active_adjoint_recovery_fail"
        ),
        "pass": passed,
        "adjoint_formula": (
            "z_i=-A_ii^-H*A_ti^H*z_t+A_ii^-H*g_i"
        ),
        "eliminated_cell_interior_equations": equations,
        "expected_cell_interior_equations": (
            system.entity_map.active_rows
            - system.entity_map.active_trace_rows
        ),
        "residual_norm": residual_norm,
        "reference_norm": reference_norm,
        "relative_residual": relative,
        "maximum_abs_residual": maximum,
        "relative_tolerance": float(relative_tolerance),
        "absolute_tolerance": float(absolute_tolerance),
        "active_full_goal_supplied": active_full_goal is not None,
        "uses_primal_recovery_operator": False,
        "ordinary_default_changed": False,
    }
    if not passed:
        raise RuntimeError(
            "variable-p active adjoint recovery failed: "
            f"equations={equations}/"
            f"{audit['expected_cell_interior_equations']}, "
            f"relative={relative:.6e}, max={maximum:.6e}"
        )
    return audit


__all__ = [
    "VariablePCellRecovery",
    "VariablePCondensedTraceSystem",
    "VariablePOwnedCellSchurAction",
    "audit_variable_p_active_full_adjoint_recovery",
    "build_variable_p_condensed_trace_system",
    "build_variable_p_condensed_trace_system_from_compiled_form",
    "condense_variable_p_active_vector_to_trace",
    "extract_variable_p_active_primal_to_reduced",
    "recover_variable_p_active_full_adjoint_vector",
    "recover_variable_p_active_full_vector",
    "retained_variable_p_owned_cell_schur_actions",
    "variable_p_cell_interior_schur_bilinear",
]
