"""Owner-local p2 slab operators and fixed ILU(0) factors.

The component keeps the p6 trace action at cell-block granularity.  For each
physical slab it gathers the already-built owner-local p2-to-p6 trace stencils
and projects each routed retained cell Schur block directly into p2 space.
No p6 slab matrix or p6 factor is created.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .physical_slab_two_level import (
    OwnerLocalSlabPlan,
    _exact_seqaij_fingerprint,
    extract_owner_local_slab_diagonal,
    _route_owner_slab_cells,
)
from .static_trace_auxiliary import (
    STRUCTURAL_ZERO_TOLERANCE,
    OwnerLocalTraceTransfer,
)

__all__ = (
    "OwnerLocalP2SlabFactor",
    "build_owner_local_p2_slab_factors",
)


@dataclass
class OwnerLocalP2SlabFactor:
    """One owner-local p2 slab operator and its retained ILU(0) factor."""

    slab: int
    owner: int
    p6_row_global_ids: np.ndarray
    p6_row_offsets: np.ndarray
    p2_column_global_ids: np.ndarray
    p2_column_ids: np.ndarray
    p2_values: np.ndarray
    matrix: PETSc.Mat | None
    factor_matrix: PETSc.Mat | None
    rhs: PETSc.Vec | None
    solution: PETSc.Vec | None
    matrix_nnz: int
    factor_nnz: int
    factor_payload_lower_bound_bytes: int
    cell_count: int
    operator_fingerprint: str
    matrix_assembled: bool
    matrix_retained: bool
    _destroyed: bool = False

    def action(self, values: np.ndarray) -> np.ndarray:
        """Apply the retained local p2 operator on its owner rank."""

        if self.matrix is None or self.rhs is None or self.solution is None:
            raise RuntimeError(
                "local p2 action is available only with retain_operator=True"
            )
        values = np.asarray(values, dtype=PETSc.ScalarType)
        if values.size != self.p2_column_global_ids.size:
            raise ValueError("local p2 action vector has an unexpected size")
        self.rhs.getArray()[:] = values
        self.rhs.assemble()
        self.matrix.mult(self.rhs, self.solution)
        return np.asarray(
            self.solution.getArray(readonly=True), dtype=PETSc.ScalarType
        ).copy()

    def prolong(self, values: np.ndarray) -> np.ndarray:
        """Apply the local forward transfer ``P_j`` to p6 slab rows."""

        values = np.asarray(values, dtype=PETSc.ScalarType)
        if values.size != self.p2_column_global_ids.size:
            raise ValueError("local p2 prolongation vector has an unexpected size")
        weighted = self.p2_values * values[self.p2_column_ids]
        result = np.zeros(self.p6_row_global_ids.size, dtype=PETSc.ScalarType)
        nonempty = np.flatnonzero(np.diff(self.p6_row_offsets))
        if nonempty.size:
            result[nonempty] = np.add.reduceat(weighted, self.p6_row_offsets[nonempty])
        return result

    def restrict_adjoint(self, values: np.ndarray) -> np.ndarray:
        """Apply the local conjugate transpose ``P_jᴴ`` to p6 slab rows."""

        values = np.asarray(values, dtype=PETSc.ScalarType)
        if values.size != self.p6_row_global_ids.size:
            raise ValueError("local p6 restriction vector has an unexpected size")
        result = np.zeros(self.p2_column_global_ids.size, dtype=PETSc.ScalarType)
        repeated = np.repeat(values, np.diff(self.p6_row_offsets))
        np.add.at(
            result,
            self.p2_column_ids,
            np.conjugate(self.p2_values) * repeated,
        )
        return result

    def solve(self, values: np.ndarray) -> np.ndarray:
        """Apply the fixed owner-local PREONLY+ILU(0) factor."""

        if self.factor_matrix is None or self.rhs is None or self.solution is None:
            raise RuntimeError("only the slab owner can solve its local factor")
        values = np.asarray(values, dtype=PETSc.ScalarType)
        if values.size != self.p2_column_global_ids.size:
            raise ValueError("local p2 solve vector has an unexpected size")
        self.rhs.getArray()[:] = values
        self.rhs.assemble()
        self.factor_matrix.solve(self.rhs, self.solution)
        return np.asarray(
            self.solution.getArray(readonly=True), dtype=PETSc.ScalarType
        ).copy()

    def destroy(self) -> None:
        if self._destroyed:
            return
        if self.factor_matrix is not None:
            self.factor_matrix.destroy()
        if self.matrix is not None:
            self.matrix.destroy()
        if self.rhs is not None:
            self.rhs.destroy()
        if self.solution is not None:
            self.solution.destroy()
        self._destroyed = True


def _local_transfer_packet(
    transfer: OwnerLocalTraceTransfer,
    condensed: Any,
    plan: OwnerLocalSlabPlan,
    slab: int,
) -> list[tuple[int, list[int], list[complex]]]:
    support_rows: set[int] = set()
    constraints = condensed.trace_constraints
    for cell in plan.local_cell_indices_by_slab[slab]:
        recovery = condensed.cell_recovery_maps[cell]
        for original in recovery.trace_original_dofs:
            active_ids, coefficients = constraints.expansion_by_original[int(original)]
            support_rows.update(
                int(active)
                for active, coefficient in zip(active_ids, coefficients, strict=True)
                if coefficient != 0
            )
    selected = np.isin(
        transfer.row_global_ids, np.fromiter(support_rows, dtype=PETSc.IntType)
    )
    packet: list[tuple[int, list[int], list[complex]]] = []
    for selected_row in np.flatnonzero(selected):
        start = int(transfer.row_offsets[selected_row])
        end = int(transfer.row_offsets[selected_row + 1])
        packet.append(
            (
                int(transfer.row_global_ids[selected_row]),
                [int(value) for value in transfer.column_ids[start:end]],
                [complex(value) for value in transfer.values[start:end]],
            )
        )
    return packet


def _gather_slab_transfer(
    transfer: OwnerLocalTraceTransfer,
    condensed: Any,
    plan: OwnerLocalSlabPlan,
    slab: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    owner = int(plan.slab_owners[slab])
    packets = plan.comm.gather(
        _local_transfer_packet(transfer, condensed, plan, slab),
        root=owner,
    )
    if plan.comm.rank != owner:
        return None
    rows = plan.owner_rows[slab]
    row_map: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for packet in packets:
        for row, columns, values in packet:
            current = row_map.get(row)
            candidate_columns = np.asarray(columns, dtype=PETSc.IntType)
            candidate_values = np.asarray(values, dtype=PETSc.ScalarType)
            if current is not None:
                previous_columns, previous_values = current
                union = np.union1d(previous_columns, candidate_columns)
                previous = np.zeros(union.size, dtype=PETSc.ScalarType)
                candidate = np.zeros(union.size, dtype=PETSc.ScalarType)
                previous[np.searchsorted(union, previous_columns)] = previous_values
                candidate[np.searchsorted(union, candidate_columns)] = candidate_values
                if float(np.max(np.abs(previous - candidate), initial=0.0)) > 1.0e-12:
                    raise RuntimeError("duplicate slab transfer rows disagree")
            else:
                row_map[row] = (candidate_columns, candidate_values)
    if set(map(int, rows)) != set(row_map):
        raise RuntimeError("slab transfer rows do not match owner row support")
    ordered = [row_map[int(row)] for row in rows]
    offsets = np.zeros(rows.size + 1, dtype=PETSc.IntType)
    offsets[1:] = np.cumsum([columns.size for columns, _values in ordered])
    column_ids = np.asarray(
        np.concatenate([columns for columns, _values in ordered]),
        dtype=PETSc.IntType,
    )
    values = np.asarray(
        np.concatenate([values for _columns, values in ordered]),
        dtype=PETSc.ScalarType,
    )
    needed = np.unique(column_ids).astype(PETSc.IntType, copy=False)
    local_columns = np.searchsorted(needed, column_ids).astype(PETSc.IntType)
    return rows.copy(), offsets, needed, local_columns, values


def _projected_entries(
    entries: dict[int, dict[int, complex]],
    active_ids: np.ndarray,
    block: np.ndarray,
    row_positions: dict[int, int],
    row_entries: list[tuple[tuple[int, complex], ...]],
) -> int:
    selected = [
        index for index, row in enumerate(active_ids) if int(row) in row_positions
    ]
    if not selected:
        raise RuntimeError("cell Schur support is outside the slab transfer")
    positions = [row_positions[int(active_ids[index])] for index in selected]
    cell_columns = sorted(
        {
            int(column)
            for position in positions
            for column, _value in row_entries[int(position)]
        }
    )
    cell_column_positions = {column: index for index, column in enumerate(cell_columns)}
    projected_transfer = np.zeros(
        (len(positions), len(cell_columns)), dtype=PETSc.ScalarType
    )
    for local_row, position in enumerate(positions):
        for column, value in row_entries[int(position)]:
            projected_transfer[local_row, cell_column_positions[int(column)]] = value
    selected_block = np.asarray(block[np.ix_(selected, selected)])
    projected = projected_transfer.conjugate().T @ selected_block @ projected_transfer
    slab_positions = np.asarray(cell_columns, dtype=PETSc.IntType)
    temporary_bytes = int(
        projected_transfer.nbytes + projected.nbytes + selected_block.nbytes
    )
    for row in range(len(cell_columns)):
        row_entries_map = entries.setdefault(int(slab_positions[row]), {})
        nonzero = np.flatnonzero(np.abs(projected[row]) > STRUCTURAL_ZERO_TOLERANCE)
        for column in nonzero:
            target = int(slab_positions[column])
            row_entries_map[target] = row_entries_map.get(target, 0.0j) + complex(
                projected[row, column]
            )
    return temporary_bytes


def _projected_diagonal_entries(
    entries: dict[int, dict[int, complex]],
    offsets: np.ndarray,
    local_columns: np.ndarray,
    values: np.ndarray,
    diagonal: np.ndarray,
) -> None:
    """Add ``P_jᴴ diag(diagonal) P_j`` once for each p6 row."""

    if diagonal.size != offsets.size - 1:
        raise ValueError("slab shift is not aligned with p6 transfer rows")
    for row, shift in enumerate(diagonal):
        start = int(offsets[row])
        end = int(offsets[row + 1])
        columns = local_columns[start:end]
        row_values = values[start:end]
        for left, left_value in zip(columns, row_values, strict=True):
            row_entries = entries.setdefault(int(left), {})
            for right, right_value in zip(columns, row_values, strict=True):
                column = int(right)
                row_entries[column] = row_entries.get(column, 0.0j) + complex(
                    np.conjugate(left_value) * shift * right_value
                )


def _factor_from_entries(
    entries: dict[int, dict[int, complex]],
    size: int,
) -> tuple[PETSc.Mat, PETSc.Mat, PETSc.Vec, PETSc.Vec, int, int, int]:
    cleaned = {
        row: {
            column: value
            for column, value in values.items()
            if abs(value) > STRUCTURAL_ZERO_TOLERANCE
        }
        for row, values in entries.items()
    }
    row_nnz = np.asarray(
        [len(cleaned.get(row, {})) for row in range(size)],
        dtype=PETSc.IntType,
    )
    if not np.any(row_nnz):
        raise RuntimeError("projected p2 slab operator is empty")
    matrix = PETSc.Mat().createAIJ(
        size=(size, size),
        nnz=row_nnz,
        comm=PETSc.COMM_SELF,
    )
    matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)
    for row in range(size):
        values = cleaned.get(row, {})
        if values:
            columns = np.asarray(sorted(values), dtype=PETSc.IntType)
            matrix.setValues(
                np.asarray([row], dtype=PETSc.IntType),
                columns,
                np.asarray(
                    [[values[int(column)] for column in columns]],
                    dtype=PETSc.ScalarType,
                ),
            )
    matrix.assemble()
    matrix_nnz = int(matrix.getInfo(PETSc.Mat.InfoType.LOCAL)["nz_used"])
    ksp = PETSc.KSP().create(PETSc.COMM_SELF)
    ksp.setOperators(matrix)
    ksp.setType("preonly")
    ksp.getPC().setType("ilu")
    ksp.getPC().setFactorLevels(0)
    ksp.getPC().setFactorOrdering("rcm")
    ksp.setUp()
    factor_matrix = ksp.getPC().getFactorMatrix()
    factor_matrix.incRef()
    factor_nnz = int(factor_matrix.getInfo(PETSc.Mat.InfoType.LOCAL)["nz_used"])
    ksp.destroy()
    rhs = matrix.createVecRight()
    solution = matrix.createVecLeft()
    payload = int(
        factor_nnz
        * (np.dtype(PETSc.ScalarType).itemsize + np.dtype(PETSc.IntType).itemsize)
        + (size + 1) * np.dtype(PETSc.IntType).itemsize
    )
    return matrix, factor_matrix, rhs, solution, matrix_nnz, factor_nnz, payload


def build_owner_local_p2_slab_factors(
    condensed: Any,
    transfer: OwnerLocalTraceTransfer,
    plan: OwnerLocalSlabPlan,
    *,
    retain_operator: bool = False,
    shifted_diagonal: PETSc.Vec | None = None,
) -> tuple[tuple[OwnerLocalP2SlabFactor, ...], dict[str, Any]]:
    """Build one owner-local p2 ``P_jᴴ A6_j P_j`` ILU(0) factor per slab.

    ``retain_operator`` is intended only for the small algebra oracle; the
    default factor-only path releases every assembled p2 matrix after its
    fingerprint and ILU(0) factor have been recorded.  When supplied,
    ``shifted_diagonal`` is projected through the same transfer as
    ``P_jᴴ diag(shifted_diagonal) P_j``.
    """

    if condensed.matrix is not None:
        raise ValueError(
            "local p2 slab factors require an action-only condensed system"
        )
    if int(transfer.fine_constraints.active_rows) != int(plan.active_rows):
        raise ValueError("p2/p6 transfer and slab plan have different fine sizes")
    if shifted_diagonal is not None and int(shifted_diagonal.getSize()) != int(
        plan.active_rows
    ):
        raise ValueError("p2 shift and slab plan have different fine sizes")
    if len(plan.slab_owners) == 0:
        raise ValueError("at least one slab is required")
    factors: list[OwnerLocalP2SlabFactor] = []
    route_audits: list[dict[str, int]] = []
    max_cell_projected_temporary_bytes = 0
    for slab, owner in enumerate(plan.slab_owners):
        gathered = _gather_slab_transfer(transfer, condensed, plan, slab)
        slab_shift, _shift_audit = (
            extract_owner_local_slab_diagonal(shifted_diagonal, plan, slab)
            if shifted_diagonal is not None
            else (None, None)
        )
        entries: dict[int, dict[int, complex]] = {}
        cell_count = 0
        row_positions: dict[int, int] | None = None
        row_entries: list[tuple[tuple[int, complex], ...]] | None = None
        if plan.comm.rank == owner:
            assert gathered is not None
            p6_rows, p6_offsets, _p2_columns, p2_local_columns, p2_values = gathered
            if shifted_diagonal is not None:
                assert slab_shift is not None
                _projected_diagonal_entries(
                    entries,
                    p6_offsets,
                    p2_local_columns,
                    p2_values,
                    slab_shift,
                )
            row_positions = {int(row): index for index, row in enumerate(p6_rows)}
            row_entries = [
                tuple(
                    zip(
                        p2_local_columns[
                            int(p6_offsets[index]) : int(p6_offsets[index + 1])
                        ],
                        p2_values[int(p6_offsets[index]) : int(p6_offsets[index + 1])],
                        strict=True,
                    )
                )
                for index in range(p6_rows.size)
            ]

        def consume(
            _cell_index: int, active_ids: np.ndarray, block: np.ndarray
        ) -> None:
            nonlocal cell_count, max_cell_projected_temporary_bytes
            assert row_positions is not None
            assert row_entries is not None
            temporary_bytes = _projected_entries(
                entries,
                active_ids,
                block,
                row_positions,
                row_entries,
            )
            cell_count += 1
            max_cell_projected_temporary_bytes = max(
                max_cell_projected_temporary_bytes,
                temporary_bytes,
            )

        route_audit = _route_owner_slab_cells(condensed, plan, slab, consume)
        route_audits.append(
            {str(key): int(value) for key, value in route_audit.items()}
        )
        if plan.comm.rank == owner:
            p6_rows, p6_offsets, p2_columns, p2_local_columns, p2_values = gathered
            matrix, factor_matrix, rhs, solution, matrix_nnz, factor_nnz, payload = (
                _factor_from_entries(entries, p2_columns.size)
            )
            operator_fingerprint = _exact_seqaij_fingerprint(matrix)
            if not retain_operator:
                matrix.destroy()
                matrix = None
        else:
            p6_rows = np.empty(0, dtype=PETSc.IntType)
            p6_offsets = np.zeros(1, dtype=PETSc.IntType)
            p2_columns = np.empty(0, dtype=PETSc.IntType)
            p2_local_columns = np.empty(0, dtype=PETSc.IntType)
            p2_values = np.empty(0, dtype=PETSc.ScalarType)
            cell_count = 0
            matrix = factor_matrix = rhs = solution = None
            matrix_nnz = factor_nnz = payload = 0
            operator_fingerprint = ""
        factor = OwnerLocalP2SlabFactor(
            slab=slab,
            owner=int(owner),
            p6_row_global_ids=p6_rows,
            p6_row_offsets=p6_offsets,
            p2_column_global_ids=p2_columns,
            p2_column_ids=p2_local_columns,
            p2_values=p2_values,
            matrix=matrix,
            factor_matrix=factor_matrix,
            rhs=rhs,
            solution=solution,
            matrix_nnz=matrix_nnz,
            factor_nnz=factor_nnz,
            factor_payload_lower_bound_bytes=payload,
            cell_count=cell_count,
            operator_fingerprint=operator_fingerprint,
            matrix_assembled=plan.comm.rank == owner,
            matrix_retained=matrix is not None,
        )
        factors.append(factor)
    local_factor_count = sum(factor.factor_matrix is not None for factor in factors)
    local_matrix_nnz = sum(factor.matrix_nnz for factor in factors)
    local_factor_nnz = sum(factor.factor_nnz for factor in factors)
    local_payload = sum(factor.factor_payload_lower_bound_bytes for factor in factors)
    local_slab_ledger = [
        {
            "slab": int(factor.slab),
            "owner": int(factor.owner),
            "p6_rows": int(factor.p6_row_global_ids.size),
            "p6_transfer_nnz": int(factor.p2_values.size),
            "p2_rows": int(factor.p2_column_global_ids.size),
            "p2_matrix_nnz": int(factor.matrix_nnz),
            "p2_factor_nnz": int(factor.factor_nnz),
            "factor_payload_lower_bound_bytes": int(
                factor.factor_payload_lower_bound_bytes
            ),
            "cell_count": int(factor.cell_count),
            "operator_fingerprint": factor.operator_fingerprint,
            "matrix_assembled": bool(factor.matrix_assembled),
            "matrix_retained": bool(factor.matrix_retained),
        }
        for factor in factors
        if factor.matrix_assembled
    ]
    slab_ledger = sorted(
        [
            record
            for packet in plan.comm.allgather(local_slab_ledger)
            for record in packet
        ],
        key=lambda record: int(record["slab"]),
    )
    if len(slab_ledger) != len(factors) or {
        int(record["slab"]) for record in slab_ledger
    } != set(range(len(factors))):
        raise RuntimeError("owner-local p2 slab ledger is incomplete")
    audit = {
        "num_slabs": len(factors),
        "local_factor_count": int(local_factor_count),
        "p2_slab_matrix_assembled_count": int(
            plan.comm.allreduce(
                sum(factor.matrix_assembled for factor in factors), op=MPI.SUM
            )
        ),
        "p2_slab_matrix_retained_count": int(
            plan.comm.allreduce(
                sum(factor.matrix_retained for factor in factors), op=MPI.SUM
            )
        ),
        "p2_factor_count": int(plan.comm.allreduce(local_factor_count, op=MPI.SUM)),
        "p2_matrix_nnz": int(plan.comm.allreduce(local_matrix_nnz, op=MPI.SUM)),
        "p2_factor_nnz": int(plan.comm.allreduce(local_factor_nnz, op=MPI.SUM)),
        "factor_payload_lower_bound_bytes": int(
            plan.comm.allreduce(local_payload, op=MPI.SUM)
        ),
        "p2_slab_rows": int(
            plan.comm.allreduce(
                sum(factor.p2_column_global_ids.size for factor in factors),
                op=MPI.SUM,
            )
        ),
        "p2_transfer_nnz": int(
            plan.comm.allreduce(
                sum(factor.p2_values.size for factor in factors),
                op=MPI.SUM,
            )
        ),
        "slab_ledger": slab_ledger,
        "route_audits": route_audits,
        "max_cell_projected_temporary_bytes": int(
            plan.comm.allreduce(max_cell_projected_temporary_bytes, op=MPI.MAX)
        ),
        "transfer_support_mode": "actual_entity_orientation_floquet_stencil_closure",
        "shift_mode": (
            "projected_same_shift"
            if shifted_diagonal is not None
            else "none_unshifted_a6_j"
        ),
        "operator_kind": "unshifted_PjH_R6_A6_R6T_Pj",
        "shift_included": shifted_diagonal is not None,
        "p6_slab_matrix_count": 0,
        "p6_factor_count": 0,
        "p6_factor_nnz": 0,
        "global_p6_matrix_materialized": False,
        "global_p6_factor_materialized": False,
        "solver_type": "preonly_ilu0",
    }
    if shifted_diagonal is not None:
        audit["operator_kind"] = "projected_same_shift_PjH_R6_(A6+S6)_R6T_Pj"
    return tuple(factors), audit
