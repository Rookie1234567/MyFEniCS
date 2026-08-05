"""Research-only global retained p4-core action and recovery.

The existing assembly-time system keeps ``active_rows`` trace-only.  This
module therefore owns a separate retained numbering with one local p4-core
block per owned cell.  Trace constraints are represented by the supplied
local sparse expansion; the cell-local core is always an identity block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy import sparse

from .hcurl_p4_core_partial_condensation import (
    P4CorePartialCondensation,
)


_CORE_ROWS_PER_CELL = 108


def _prefix_offsets(counts: Sequence[int]) -> tuple[int, ...]:
    offsets = [0]
    for count in counts:
        offsets.append(offsets[-1] + int(count))
    return tuple(offsets)


@dataclass(frozen=True)
class RetainedP4CoreNumbering:
    """Rank-contiguous retained numbering for trace plus cell-local core."""

    comm: MPI.Intracomm = field(repr=False, compare=False)
    active_trace_rows: int
    owned_active_trace_rows: int
    global_cells: int
    local_cells: int
    active_rank_offsets: tuple[int, ...]
    retained_rank_offsets: tuple[int, ...]
    cell_core_global_ids: tuple[np.ndarray, ...]
    retained_rows: int
    owned_retained_rows: int
    audit: dict[str, object]

    def create_retained_vector(self) -> PETSc.Vec:
        """Create a Vec with the retained rank-contiguous ownership."""

        return PETSc.Vec().createMPI(
            (self.owned_retained_rows, self.retained_rows),
            comm=self.comm,
        )

    def map_active_ids(self, active_ids: np.ndarray) -> np.ndarray:
        """Map old active-trace ids into the new rank-block numbering."""

        values = np.asarray(active_ids, dtype=np.int64).reshape(-1)
        if values.size and (
            int(values.min()) < 0 or int(values.max()) >= self.active_trace_rows
        ):
            raise ValueError("active trace ids are outside the old numbering")
        active_offsets = np.asarray(self.active_rank_offsets, dtype=np.int64)
        retained_offsets = np.asarray(
            self.retained_rank_offsets,
            dtype=np.int64,
        )
        owners = np.searchsorted(active_offsets[1:], values, side="right")
        if np.any(owners >= self.comm.size):
            raise ValueError("active trace id has no owning rank")
        mapped = retained_offsets[owners] + values - active_offsets[owners]
        return np.asarray(mapped, dtype=PETSc.IntType)


def build_retained_p4_core_numbering(
    *,
    comm: MPI.Intracomm,
    active_trace_rows: int,
    owned_active_trace_rows: int,
    local_cell_count: int,
) -> RetainedP4CoreNumbering:
    """Build rank-contiguous trace-plus-cell-core numbering."""

    active_counts = tuple(
        int(value) for value in comm.allgather(int(owned_active_trace_rows))
    )
    if sum(active_counts) != int(active_trace_rows):
        raise ValueError("owned active trace counts do not close globally")
    cell_counts = tuple(int(value) for value in comm.allgather(int(local_cell_count)))
    retained_counts = tuple(
        active + _CORE_ROWS_PER_CELL * cells
        for active, cells in zip(active_counts, cell_counts, strict=True)
    )
    active_offsets = _prefix_offsets(active_counts)
    retained_offsets = _prefix_offsets(retained_counts)
    core_start = retained_offsets[comm.rank] + int(owned_active_trace_rows)
    core_ids = tuple(
        np.arange(
            core_start + _CORE_ROWS_PER_CELL * cell,
            core_start + _CORE_ROWS_PER_CELL * (cell + 1),
            dtype=PETSc.IntType,
        )
        for cell in range(int(local_cell_count))
    )
    retained_rows = int(retained_offsets[-1])
    audit = {
        "schema_version": "task037.r7b1.retained-p4-core-numbering.v1",
        "active_trace_rows": int(active_trace_rows),
        "global_cells": int(sum(cell_counts)),
        "local_cells": int(local_cell_count),
        "core_rows_per_cell": _CORE_ROWS_PER_CELL,
        "global_core_rows": int(sum(cell_counts) * _CORE_ROWS_PER_CELL),
        "retained_rows": retained_rows,
        "owned_retained_rows": int(retained_counts[comm.rank]),
        "active_rank_offsets": active_offsets,
        "retained_rank_offsets": retained_offsets,
        "rank_contiguous_ownership": True,
        "core_owner_is_cell_rank": True,
        "trace_mpc_only": True,
        "research_only": True,
        "ordinary_default_changed": False,
    }
    return RetainedP4CoreNumbering(
        comm=comm,
        active_trace_rows=int(active_trace_rows),
        owned_active_trace_rows=int(owned_active_trace_rows),
        global_cells=int(sum(cell_counts)),
        local_cells=int(local_cell_count),
        active_rank_offsets=active_offsets,
        retained_rank_offsets=retained_offsets,
        cell_core_global_ids=core_ids,
        retained_rows=retained_rows,
        owned_retained_rows=int(retained_counts[comm.rank]),
        audit=audit,
    )


@dataclass(frozen=True)
class _RetainedCell:
    factor: P4CorePartialCondensation
    retained_global_ids: np.ndarray
    expansion: sparse.csr_matrix
    cell_original_dofs: np.ndarray | None = None

    def contribution(self) -> tuple[np.ndarray, np.ndarray]:
        """Return global ids and the constrained local block."""

        block = self.expansion.conjugate().transpose() @ (
            self.factor.partial_schur @ self.expansion
        )
        return (
            self.retained_global_ids.copy(),
            np.asarray(block, dtype=PETSc.ScalarType),
        )


class _RetainedScatter:
    def __init__(self, system: RetainedP4CoreSystem) -> None:
        cell_ids = [cell.retained_global_ids for cell in system.cells]
        union = (
            np.unique(np.concatenate(cell_ids))
            if cell_ids
            else np.empty(0, dtype=PETSc.IntType)
        )
        self.union_indices = np.asarray(union, dtype=PETSc.IntType)
        self.cells = tuple(
            (
                cell,
                np.asarray(
                    np.searchsorted(self.union_indices, cell.retained_global_ids),
                    dtype=PETSc.IntType,
                ),
            )
            for cell in system.cells
        )
        template = system.create_retained_vector()
        self.source = PETSc.Vec().createSeq(
            len(self.union_indices),
            comm=PETSc.COMM_SELF,
        )
        self.target = self.source.duplicate()
        global_is = PETSc.IS().createGeneral(
            self.union_indices,
            comm=PETSc.COMM_SELF,
        )
        local_is = PETSc.IS().createStride(
            len(self.union_indices),
            first=0,
            step=1,
            comm=PETSc.COMM_SELF,
        )
        self.scatter = PETSc.Scatter().create(
            template,
            global_is,
            self.source,
            local_is,
        )
        local_is.destroy()
        global_is.destroy()
        template.destroy()
        self._destroyed = False

    def forward(self, source: PETSc.Vec) -> None:
        self.source.set(0.0)
        self.scatter.scatter(
            source,
            self.source,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )

    def reverse(self, target: PETSc.Vec) -> None:
        self.scatter.scatter(
            self.target,
            target,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )

    def destroy(self) -> None:
        if not self._destroyed:
            self.scatter.destroy()
            self.target.destroy()
            self.source.destroy()
            self._destroyed = True


class _RetainedActionContext:
    def __init__(self, system: RetainedP4CoreSystem) -> None:
        self._scatter = _RetainedScatter(system)
        self._destroyed = False

    def mult(
        self,
        _matrix: PETSc.Mat,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        target.set(0.0)
        self._scatter.forward(source)
        source_values = self._scatter.source.getArray(readonly=True)
        self._scatter.target.set(0.0)
        target_values = self._scatter.target.getArray()
        for cell, positions in self._scatter.cells:
            local_values = cell.expansion @ source_values[positions]
            local_action = cell.factor.partial_schur @ local_values
            target_values[positions] += np.asarray(
                cell.expansion.conjugate().transpose() @ local_action,
                dtype=PETSc.ScalarType,
            )
        self._scatter.reverse(target)

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if not self._destroyed:
            self._scatter.destroy()
            self._destroyed = True


@dataclass(frozen=True)
class RetainedP4CoreSystem:
    """Global retained action, RHS reduction, and full p6 recovery."""

    numbering: RetainedP4CoreNumbering
    cells: tuple[_RetainedCell, ...]
    audit: dict[str, object]
    trace_constraints: object | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    owned_trace_original_dofs: np.ndarray | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    full_rows: int | None = field(default=None, repr=False, compare=False)

    @property
    def comm(self) -> MPI.Intracomm:
        return self.numbering.comm

    @property
    def retained_rows(self) -> int:
        return self.numbering.retained_rows

    def create_retained_vector(self) -> PETSc.Vec:
        return self.numbering.create_retained_vector()

    def cell_contribution(
        self,
        cell_index: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        return self.cells[int(cell_index)].contribution()

    def create_retained_action(self) -> tuple[PETSc.Mat, _RetainedActionContext]:
        """Create a collective PETSc matrix-free retained action."""

        context = _RetainedActionContext(self)
        sizes = (
            (
                self.numbering.owned_retained_rows,
                self.numbering.retained_rows,
            ),
            (
                self.numbering.owned_retained_rows,
                self.numbering.retained_rows,
            ),
        )
        action = PETSc.Mat().createPython(
            sizes,
            context=context,
            comm=self.comm,
        )
        action.setUp()
        return action, context

    def _assemble_local_vectors(
        self,
        local_vectors: Sequence[np.ndarray],
    ) -> PETSc.Vec:
        if len(local_vectors) != len(self.cells):
            raise ValueError("one local vector is required per retained cell")
        scatter = _RetainedScatter(self)
        scatter.target.set(0.0)
        target_values = scatter.target.getArray()
        for (cell, positions), local_vector in zip(
            scatter.cells,
            local_vectors,
            strict=True,
        ):
            values = np.asarray(local_vector, dtype=PETSc.ScalarType)
            if values.shape != (540,):
                raise ValueError("local retained RHS must have length 540")
            target_values[positions] += np.asarray(
                cell.expansion.conjugate().transpose() @ values,
                dtype=PETSc.ScalarType,
            )
        result = self.create_retained_vector()
        scatter.reverse(result)
        scatter.destroy()
        return result

    def assemble_retained_rhs(
        self,
        *,
        reference_rhs_by_cell: Sequence[np.ndarray] | None = None,
        oriented_rhs_by_cell: Sequence[np.ndarray] | None = None,
    ) -> PETSc.Vec:
        """Assemble the exact constrained retained RHS from local data."""

        if reference_rhs_by_cell is not None and oriented_rhs_by_cell is not None:
            raise ValueError("provide reference or oriented RHS, not both")
        if reference_rhs_by_cell is not None:
            if len(reference_rhs_by_cell) != len(self.cells):
                raise ValueError("one reference RHS is required per cell")
            local = tuple(
                cell.factor.reduce_reference_rhs(rhs)
                for cell, rhs in zip(
                    self.cells,
                    reference_rhs_by_cell,
                    strict=True,
                )
            )
        elif oriented_rhs_by_cell is not None:
            if len(oriented_rhs_by_cell) != len(self.cells):
                raise ValueError("one oriented RHS is required per cell")
            local = tuple(
                cell.factor.reduce_oriented_right_rhs(rhs)
                for cell, rhs in zip(
                    self.cells,
                    oriented_rhs_by_cell,
                    strict=True,
                )
            )
        else:
            local = tuple(cell.factor.partial_rhs for cell in self.cells)
        return self._assemble_local_vectors(local)

    def assemble_retained_left_functional(
        self,
        oriented_functional_by_cell: Sequence[np.ndarray],
    ) -> PETSc.Vec:
        """Assemble exact left row-functionals in retained coordinates."""

        if len(oriented_functional_by_cell) != len(self.cells):
            raise ValueError("one left functional is required per cell")
        local = tuple(
            cell.factor.reduce_oriented_left_functional(functional)
            for cell, functional in zip(
                self.cells,
                oriented_functional_by_cell,
                strict=True,
            )
        )
        return self._assemble_local_vectors(local)

    def reduce_reference_rhs_by_cell(
        self,
        reference_rhs_by_cell: Sequence[np.ndarray],
    ) -> tuple[np.ndarray, ...]:
        """Return exact right/load reductions for local reference RHS."""

        if len(reference_rhs_by_cell) != len(self.cells):
            raise ValueError("one reference RHS is required per cell")
        return tuple(
            cell.factor.reduce_reference_rhs(rhs)
            for cell, rhs in zip(self.cells, reference_rhs_by_cell, strict=True)
        )

    def _create_full_fe_reduction(
        self,
        full_vector: PETSc.Vec,
    ) -> tuple[PETSc.Vec, tuple[np.ndarray, ...]]:
        """Create a trace-once reduction and return owned cell interiors."""

        values, row_start, interiors = self._full_fe_owned_parts(full_vector)
        result = self.create_retained_vector()
        accumulated: dict[int, complex] = {}
        constraints = self.trace_constraints
        row_end = row_start + len(values)
        for original in self.owned_trace_original_dofs:
            row = int(original)
            if row < row_start or row >= row_end:
                raise ValueError("owned trace row is outside FE vector ownership")
            active_ids, coefficients = constraints.expansion_by_original[row]
            mapped = self.numbering.map_active_ids(active_ids)
            for retained_id, coefficient in zip(mapped, coefficients, strict=True):
                key = int(retained_id)
                accumulated[key] = accumulated.get(key, 0.0j) + (
                    np.conj(coefficient) * values[row - row_start]
                )
        if accumulated:
            result.setValues(
                np.asarray(tuple(accumulated), dtype=PETSc.IntType),
                np.asarray(tuple(accumulated.values()), dtype=PETSc.ScalarType),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
        result.assemble()
        return result, interiors

    def _full_fe_owned_parts(
        self,
        full_vector: PETSc.Vec,
    ) -> tuple[np.ndarray, int, tuple[np.ndarray, ...]]:
        if (
            self.trace_constraints is None
            or self.owned_trace_original_dofs is None
            or self.full_rows is None
        ):
            raise ValueError(
                "full FE reduction requires compiled-form retained metadata"
            )
        if full_vector.getSize() != int(self.full_rows):
            raise ValueError("full FE vector size differs from retained metadata")
        row_start, row_end = map(int, full_vector.getOwnershipRange())
        values = np.asarray(
            full_vector.getArray(readonly=True),
            dtype=PETSc.ScalarType,
        )
        interiors = []
        for cell in self.cells:
            if cell.cell_original_dofs is None:
                raise ValueError(
                    "compiled-form cell metadata is required for FE reduction"
                )
            rows = np.asarray(
                cell.cell_original_dofs[cell.factor.p6_interior_dofs],
                dtype=np.int64,
            )
            if len(rows) and (
                int(rows.min()) < row_start or int(rows.max()) >= row_end
            ):
                raise ValueError("owned cell interior is outside FE ownership")
            interiors.append(values[rows - row_start].copy())
        return values, row_start, tuple(interiors)

    def reduce_full_fe_right_rhs(self, full_vector: PETSc.Vec) -> PETSc.Vec:
        """Reduce an assembled unconstrained full FE load from the right."""

        result, interiors = self._create_full_fe_reduction(full_vector)
        scatter = _RetainedScatter(self)
        scatter.target.set(0.0)
        target_values = scatter.target.getArray()
        for (cell, positions), values in zip(
            scatter.cells,
            interiors,
            strict=True,
        ):
            local = np.zeros(882, dtype=PETSc.ScalarType)
            local[cell.factor.p6_interior_dofs] = values
            reduced = cell.factor.reduce_oriented_right_rhs(local)
            target_values[positions] += np.asarray(
                cell.expansion.conjugate().transpose() @ reduced,
                dtype=PETSc.ScalarType,
            )
        scatter.reverse(result)
        scatter.destroy()
        result.assemble()
        return result

    def reduce_full_fe_left_functional(
        self,
        full_vector: PETSc.Vec,
    ) -> PETSc.Vec:
        """Reduce an assembled unconstrained full FE row-functional."""

        result, interiors = self._create_full_fe_reduction(full_vector)
        scatter = _RetainedScatter(self)
        scatter.target.set(0.0)
        target_values = scatter.target.getArray()
        for (cell, positions), values in zip(
            scatter.cells,
            interiors,
            strict=True,
        ):
            local = np.zeros(882, dtype=PETSc.ScalarType)
            local[cell.factor.p6_interior_dofs] = values
            reduced = cell.factor.reduce_oriented_left_functional(local)
            target_values[positions] += np.asarray(
                cell.expansion.conjugate().transpose() @ reduced,
                dtype=PETSc.ScalarType,
            )
        scatter.reverse(result)
        scatter.destroy()
        result.assemble()
        return result

    def eliminated_complement_bilinear_full_fe(
        self,
        left_vector: PETSc.Vec,
        right_vector: PETSc.Vec,
    ) -> complex:
        """Evaluate the eliminated bilinear form from full FE vectors."""

        _left_values, _left_start, left_interiors = self._full_fe_owned_parts(
            left_vector
        )
        _right_values, _right_start, right_interiors = self._full_fe_owned_parts(
            right_vector
        )
        local_value = 0.0 + 0.0j
        for cell, left, right in zip(
            self.cells,
            left_interiors,
            right_interiors,
            strict=True,
        ):
            left_local = np.zeros(882, dtype=PETSc.ScalarType)
            right_local = np.zeros(882, dtype=PETSc.ScalarType)
            left_local[cell.factor.p6_interior_dofs] = left
            right_local[cell.factor.p6_interior_dofs] = right
            local_value += cell.factor.eliminated_complement_bilinear(
                left_local,
                right_local,
            )
        return complex(self.comm.allreduce(local_value, op=MPI.SUM))

    def recover_owned_full_fe_interiors(
        self,
        retained_vector: PETSc.Vec,
        full_rhs: PETSc.Vec,
    ) -> tuple[tuple[np.ndarray, np.ndarray], ...]:
        """Recover original interior rows from a retained vector and FE RHS."""

        _rhs_values, _rhs_start, rhs_interiors = self._full_fe_owned_parts(full_rhs)
        scatter = _RetainedScatter(self)
        scatter.forward(retained_vector)
        source_values = scatter.source.getArray(readonly=True)
        recovered = []
        for index, (cell, positions) in enumerate(scatter.cells):
            local_retained = cell.expansion @ source_values[positions]
            local_rhs = np.zeros(882, dtype=PETSc.ScalarType)
            local_rhs[cell.factor.p6_interior_dofs] = rhs_interiors[index]
            values = cell.factor.recover_p6_coefficients(
                local_retained,
                oriented_rhs=local_rhs,
            )
            assert cell.cell_original_dofs is not None
            rows = np.asarray(
                cell.cell_original_dofs[cell.factor.p6_interior_dofs],
                dtype=PETSc.IntType,
            )
            recovered.append((rows, values[cell.factor.p6_interior_dofs]))
        scatter.destroy()
        return tuple(recovered)

    def project_full_fe_solution(
        self,
        oriented_solution_by_cell: Sequence[np.ndarray],
    ) -> tuple[np.ndarray, ...]:
        """Return local right projections of full p6 solutions."""

        if len(oriented_solution_by_cell) != len(self.cells):
            raise ValueError("one oriented solution is required per cell")
        return tuple(
            cell.factor.project_oriented_solution(values)
            for cell, values in zip(
                self.cells,
                oriented_solution_by_cell,
                strict=True,
            )
        )

    def eliminated_complement_bilinear(
        self,
        left_oriented_by_cell: Sequence[np.ndarray],
        right_oriented_by_cell: Sequence[np.ndarray],
    ) -> complex:
        """Sum exact ``left_e^H Aee^-1 right_e`` cell contributions."""

        if len(left_oriented_by_cell) != len(self.cells) or len(
            right_oriented_by_cell
        ) != len(self.cells):
            raise ValueError("one left and right vector is required per cell")
        local_value = sum(
            (
                cell.factor.eliminated_complement_bilinear(left, right)
                for cell, left, right in zip(
                    self.cells,
                    left_oriented_by_cell,
                    right_oriented_by_cell,
                    strict=True,
                )
            ),
            0.0 + 0.0j,
        )
        return complex(self.comm.allreduce(local_value, op=MPI.SUM))

    def recover_owned_cell_p6(
        self,
        retained_vector: PETSc.Vec,
        *,
        reference_rhs_by_cell: Sequence[np.ndarray] | None = None,
        oriented_rhs_by_cell: Sequence[np.ndarray] | None = None,
    ) -> tuple[np.ndarray, ...]:
        """Recover complete oriented p6 coefficients for owned cells."""

        if reference_rhs_by_cell is not None and oriented_rhs_by_cell is not None:
            raise ValueError("provide reference or oriented RHS, not both")
        if reference_rhs_by_cell is not None:
            if len(reference_rhs_by_cell) != len(self.cells):
                raise ValueError("one reference RHS is required per cell")
            oriented_rhs_by_cell = tuple(
                cell.factor.orient_reference_vector(rhs)
                for cell, rhs in zip(
                    self.cells,
                    reference_rhs_by_cell,
                    strict=True,
                )
            )
        if oriented_rhs_by_cell is not None and len(oriented_rhs_by_cell) != len(
            self.cells
        ):
            raise ValueError("one oriented RHS is required per cell")
        scatter = _RetainedScatter(self)
        scatter.forward(retained_vector)
        source_values = scatter.source.getArray(readonly=True)
        recovered = []
        for index, (cell, positions) in enumerate(scatter.cells):
            local_retained = cell.expansion @ source_values[positions]
            rhs = None if oriented_rhs_by_cell is None else oriented_rhs_by_cell[index]
            recovered.append(
                cell.factor.recover_p6_coefficients(
                    local_retained,
                    oriented_rhs=rhs,
                )
            )
        scatter.destroy()
        return tuple(recovered)


def build_global_retained_p4_core_system(
    local_factors: Sequence[P4CorePartialCondensation],
    *,
    comm: MPI.Intracomm,
    active_trace_rows: int,
    owned_active_trace_rows: int,
    cell_trace_ids: Sequence[np.ndarray],
    cell_trace_expansions: Sequence[sparse.spmatrix],
    cell_original_dofs: Sequence[np.ndarray] | None = None,
    trace_constraints: object | None = None,
    owned_trace_original_dofs: np.ndarray | None = None,
    full_rows: int | None = None,
) -> RetainedP4CoreSystem:
    """Build a research-only global retained system from owned local factors."""

    if len(local_factors) != len(cell_trace_ids) or len(local_factors) != len(
        cell_trace_expansions
    ):
        raise ValueError("factor, trace-id, and expansion counts must agree")
    if cell_original_dofs is not None and len(cell_original_dofs) != len(local_factors):
        raise ValueError("one original-dof map is required per local factor")
    if (trace_constraints is None) != (owned_trace_original_dofs is None):
        raise ValueError("full FE metadata must include trace ownership and map")
    if trace_constraints is not None and full_rows is None:
        raise ValueError("full FE metadata requires full_rows")
    numbering = build_retained_p4_core_numbering(
        comm=comm,
        active_trace_rows=active_trace_rows,
        owned_active_trace_rows=owned_active_trace_rows,
        local_cell_count=len(local_factors),
    )
    cells = []
    for index, (factor, old_ids, trace_expansion) in enumerate(
        zip(
            local_factors,
            cell_trace_ids,
            cell_trace_expansions,
            strict=True,
        )
    ):
        if factor.partial_schur.shape != (540, 540):
            raise ValueError("each local factor must retain 540 rows")
        old_ids = np.asarray(old_ids, dtype=PETSc.IntType).reshape(-1)
        if len(np.unique(old_ids)) != old_ids.size:
            raise ValueError("cell trace ids must be locally unique")
        expansion = sparse.csr_matrix(trace_expansion, dtype=PETSc.ScalarType)
        if expansion.shape != (432, old_ids.size):
            raise ValueError("trace expansion must have 432 local rows")
        mapped_trace_ids = numbering.map_active_ids(old_ids)
        core_ids = numbering.cell_core_global_ids[index]
        retained_ids = np.concatenate((mapped_trace_ids, core_ids))
        combined = sparse.block_diag(
            (
                expansion,
                sparse.eye(
                    _CORE_ROWS_PER_CELL,
                    dtype=PETSc.ScalarType,
                    format="csr",
                ),
            ),
            format="csr",
        )
        cells.append(
            _RetainedCell(
                factor=factor,
                retained_global_ids=np.asarray(
                    retained_ids,
                    dtype=PETSc.IntType,
                ),
                expansion=combined,
                cell_original_dofs=(
                    None
                    if cell_original_dofs is None
                    else np.asarray(cell_original_dofs[index], dtype=PETSc.IntType)
                ),
            )
        )
    unique_factors = {id(cell.factor): cell.factor for cell in cells}
    partial_schur_bytes = sum(
        int(factor.partial_schur.nbytes) for factor in unique_factors.values()
    )
    eliminated_factor_bytes = sum(
        int(sum(part.nbytes for part in factor.eliminated_factor))
        for factor in unique_factors.values()
    )
    basis_bytes = sum(
        int(
            factor.core_basis.nbytes
            + factor.eliminated_basis.nbytes
            + factor.eliminated_from_retained.nbytes
            + factor.eliminated_load.nbytes
            + factor.eliminated_rhs_projection.nbytes
        )
        for factor in unique_factors.values()
    )
    map_bytes = sum(
        int(
            cell.retained_global_ids.nbytes
            + cell.expansion.data.nbytes
            + cell.expansion.indices.nbytes
            + cell.expansion.indptr.nbytes
            + (0 if cell.cell_original_dofs is None else cell.cell_original_dofs.nbytes)
        )
        for cell in cells
    )
    numbering_bytes = sum(int(array.nbytes) for array in numbering.cell_core_global_ids)
    ledger_local = {
        "partial_schur_bytes": partial_schur_bytes,
        "eliminated_factor_bytes": eliminated_factor_bytes,
        "basis_bytes": basis_bytes,
        "maps_bytes": map_bytes,
        "numbering_bytes": numbering_bytes,
    }
    audit = {
        "schema_version": "task037.r7b1.global-retained-p4-core.v1",
        **numbering.audit,
        "cell_count_local": len(cells),
        "trace_block_rows": 432,
        "retained_block_rows": 540,
        "eliminated_complement_rows_per_cell": 342,
        "eliminated_complement_rows_global": 342 * numbering.global_cells,
        "global_p6_matrix_materialized": False,
        "global_p6_factor_count": 0,
        "global_p6_factor_nnz": 0,
        "raw_p6_tensor_retained": False,
        "core_is_cell_local_identity": True,
        "research_only": True,
        "ordinary_default_changed": False,
        "full_fe_reduction_available": trace_constraints is not None,
        "global_p6_matrix_or_factor_bytes": 0,
        "retained_storage_bytes_local": int(sum(ledger_local.values())),
        "retained_storage_bytes_global": int(
            comm.allreduce(sum(ledger_local.values()), op=MPI.SUM)
        ),
        "byte_ledger_local": ledger_local,
        "byte_ledger_global": {
            key: int(comm.allreduce(value, op=MPI.SUM))
            for key, value in ledger_local.items()
        },
    }
    return RetainedP4CoreSystem(
        numbering=numbering,
        cells=tuple(cells),
        audit=audit,
        trace_constraints=trace_constraints,
        owned_trace_original_dofs=(
            None
            if owned_trace_original_dofs is None
            else np.asarray(owned_trace_original_dofs, dtype=PETSc.IntType)
        ),
        full_rows=None if full_rows is None else int(full_rows),
    )


__all__ = (
    "RetainedP4CoreNumbering",
    "RetainedP4CoreSystem",
    "build_global_retained_p4_core_system",
    "build_retained_p4_core_numbering",
)
