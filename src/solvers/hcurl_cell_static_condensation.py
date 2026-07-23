"""Exact cell-interior static condensation for assembled H(curl) systems.

This research path forms a physically smaller trace matrix.  It does not mask
or penalize inactive rows.  The current implementation starts from an already
assembled full matrix, so it reduces factorization rows but does not yet avoid
the cost or peak associated with full high-order element assembly.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Iterable

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc


def _idx(values: Iterable[int] | np.ndarray) -> np.ndarray:
    if isinstance(values, np.ndarray):
        return np.asarray(values, dtype=PETSc.IntType)
    return np.fromiter(values, dtype=PETSc.IntType)


def owned_hcurl_cell_interior_dofs(function_space) -> tuple[np.ndarray, ...]:
    """Return original global interior DoFs for every locally owned H(curl) cell."""

    dofmap = function_space.dofmap
    if int(dofmap.index_map_bs) != 1:
        raise NotImplementedError(
            "cell-interior condensation currently requires scalar-blocked H(curl)"
        )
    mesh = function_space.mesh
    tdim = mesh.topology.dim
    basix_element = function_space.element.basix_element
    entity_dofs = basix_element.entity_dofs
    if len(entity_dofs) <= tdim or len(entity_dofs[tdim]) != 1:
        raise ValueError("function space does not expose one cell-interior entity")
    cell_positions = np.asarray(entity_dofs[tdim][0], dtype=np.int32)
    if len(cell_positions) == 0:
        raise ValueError("selected H(curl) element has no cell-interior DoFs")
    owned_cells = int(mesh.topology.index_map(tdim).size_local)
    result: list[np.ndarray] = []
    for cell in range(owned_cells):
        local_cell_dofs = np.asarray(dofmap.cell_dofs(cell), dtype=np.int32)
        local_interior = local_cell_dofs[cell_positions]
        result.append(
            np.asarray(
                dofmap.index_map.local_to_global(local_interior),
                dtype=PETSc.IntType,
            )
        )
    return tuple(result)


@dataclass
class CellStaticCondensationSystem:
    """Explicit trace Schur system plus the numbering needed for recovery."""

    matrix: PETSc.Mat
    rhs: PETSc.Vec
    owned_trace_original_dofs: np.ndarray
    original_to_trace: dict[int, int]
    owned_cell_interiors: tuple[np.ndarray, ...]
    full_rows: int
    trace_rows: int
    interior_rows: int
    build_audit: dict[str, Any]

    def destroy(self) -> None:
        self.rhs.destroy()
        self.matrix.destroy()


def _validated_owned_cell_interiors(
    A: PETSc.Mat,
    owned_cell_interiors: Iterable[Iterable[int] | np.ndarray],
) -> tuple[np.ndarray, ...]:
    row_start, row_end = A.getOwnershipRange()
    cells: list[np.ndarray] = []
    flattened: list[np.ndarray] = []
    for values in owned_cell_interiors:
        dofs = np.unique(_idx(values))
        if len(dofs) == 0:
            raise ValueError("each condensed cell must contain interior DoFs")
        if int(dofs[0]) < row_start or int(dofs[-1]) >= row_end:
            raise ValueError(
                "owned cell-interior DoFs must belong to the local matrix row range"
            )
        cells.append(dofs)
        flattened.append(dofs)
    local = (
        np.concatenate(flattened)
        if flattened
        else np.empty(0, dtype=PETSc.IntType)
    )
    if len(np.unique(local)) != len(local):
        raise ValueError("cell-interior DoFs must be unique on each rank")
    comm = A.getComm().tompi4py()
    packets = comm.allgather(np.asarray(local, dtype=np.int64))
    global_values = (
        np.concatenate(packets) if packets else np.empty(0, dtype=np.int64)
    )
    if len(np.unique(global_values)) != len(global_values):
        raise ValueError("cell-interior DoFs must be globally unique")
    return tuple(cells)


def _trace_numbering(
    A: PETSc.Mat,
    cells: tuple[np.ndarray, ...],
) -> tuple[np.ndarray, dict[int, int], int]:
    comm = A.getComm().tompi4py()
    row_start, row_end = A.getOwnershipRange()
    local_interior = (
        np.concatenate(cells)
        if cells
        else np.empty(0, dtype=PETSc.IntType)
    )
    owned_rows = np.arange(row_start, row_end, dtype=PETSc.IntType)
    owned_trace = owned_rows[
        ~np.isin(owned_rows, local_interior, assume_unique=True)
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
    for originals, condensed in packets:
        mapping.update(
            (int(original), int(trace))
            for original, trace in zip(originals, condensed, strict=True)
        )
    trace_rows = int(sum(counts))
    if len(mapping) != trace_rows:
        raise RuntimeError("trace numbering is not globally unique")
    return owned_trace, mapping, trace_rows


def _row_trace_columns(
    matrix: PETSc.Mat,
    interior_rows: np.ndarray,
    cell_interior_set: set[int],
) -> np.ndarray:
    columns: set[int] = set()
    for row in interior_rows:
        row_columns, row_values = matrix.getRow(int(row))
        for column, value in zip(row_columns, row_values, strict=True):
            if int(column) not in cell_interior_set and complex(value) != 0.0:
                columns.add(int(column))
    return _idx(sorted(columns))


def _dense_cell_blocks(
    A: PETSc.Mat,
    A_transpose: PETSc.Mat,
    b: PETSc.Vec,
    interior: np.ndarray,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    interior_set = set(int(value) for value in interior)
    trace_columns = _row_trace_columns(A, interior, interior_set)
    trace_rows = _row_trace_columns(A_transpose, interior, interior_set)
    A_ii = np.asarray(
        A.getValues(interior, interior),
        dtype=np.complex128,
    )
    A_it = np.asarray(
        A.getValues(interior, trace_columns),
        dtype=np.complex128,
    )
    # A_transpose[I, T] = A[T, I]; no conjugation is introduced.
    A_ti = np.asarray(
        A_transpose.getValues(interior, trace_rows),
        dtype=np.complex128,
    ).T
    b_i = np.asarray(b.getValues(interior), dtype=np.complex128)
    return A_ii, A_it, A_ti, b_i, trace_rows, trace_columns


def build_explicit_cell_static_condensation(
    A: PETSc.Mat,
    b: PETSc.Vec,
    owned_cell_interiors: Iterable[Iterable[int] | np.ndarray],
) -> CellStaticCondensationSystem:
    """Form ``A_tt - sum(A_ti A_ii^-1 A_it)`` and its condensed RHS.

    ``owned_cell_interiors`` must contain one array per locally owned cell.
    Each interior DoF must be owned by the same rank as that cell.  The routine
    retains no all-cell dense factor cache: each cell contribution is solved,
    inserted, and released before the next cell.
    """

    if A.getSize()[0] != A.getSize()[1] or b.getSize() != A.getSize()[0]:
        raise ValueError("static condensation requires a square matrix and aligned RHS")
    comm = A.getComm().tompi4py()
    started = perf_counter()
    cells = _validated_owned_cell_interiors(A, owned_cell_interiors)
    owned_trace, mapping, trace_rows = _trace_numbering(A, cells)
    full_rows = int(A.getSize()[0])
    interior_rows = full_rows - trace_rows
    if interior_rows <= 0 or trace_rows <= 0:
        raise ValueError("static condensation requires both interior and trace rows")

    trace_is = PETSc.IS().createGeneral(owned_trace, comm=A.getComm())
    try:
        trace_submatrix = A.createSubMatrix(trace_is, trace_is)
    finally:
        trace_is.destroy()
    # MatAXPY/new-pattern insertion into a parallel submatrix is unreliable in
    # the qualified PETSc 3.19 stack.  Reinsert the trace block into a fresh
    # AIJ so PETSc owns a canonical off-diagonal map before Schur fill is added.
    trace_row_start, trace_row_end = trace_submatrix.getOwnershipRange()
    local_trace_rows = trace_row_end - trace_row_start
    diagonal_nnz = np.zeros(local_trace_rows, dtype=PETSc.IntType)
    off_diagonal_nnz = np.zeros(local_trace_rows, dtype=PETSc.IntType)
    for trace_row in range(trace_row_start, trace_row_end):
        trace_columns, _trace_values = trace_submatrix.getRow(trace_row)
        diagonal = (trace_columns >= trace_row_start) & (
            trace_columns < trace_row_end
        )
        local_row = trace_row - trace_row_start
        diagonal_nnz[local_row] = int(np.count_nonzero(diagonal))
        off_diagonal_nnz[local_row] = int(len(trace_columns) - diagonal_nnz[local_row])
    condensed = PETSc.Mat().createAIJ(
        size=trace_submatrix.getSizes(),
        nnz=(diagonal_nnz, off_diagonal_nnz),
        comm=A.getComm(),
    )
    condensed.setOption(
        PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR,
        False,
    )
    for trace_row in range(trace_row_start, trace_row_end):
        trace_columns, trace_values = trace_submatrix.getRow(trace_row)
        if len(trace_columns):
            condensed.setValues(
                _idx([trace_row]),
                _idx(trace_columns),
                np.asarray(trace_values, dtype=PETSc.ScalarType),
            )
    if local_trace_rows:
        del trace_columns, trace_values, _trace_values
    trace_submatrix.destroy()
    condensed.assemble()
    condensed_rhs = condensed.createVecRight()
    if len(owned_trace):
        condensed_rhs.getArray()[:] = np.asarray(
            b.getValues(owned_trace), dtype=PETSc.ScalarType
        )
    condensed_rhs.assemble()

    transpose_started = perf_counter()
    # petsc4py 3.19 Mat.transpose() is in-place when no output is supplied.
    # Transpose a copy so the full operator remains authoritative for recovery
    # and the explicit true-residual Gate.
    A_transpose = A.copy()
    A_transpose.transpose()
    transpose_seconds = float(
        comm.allreduce(perf_counter() - transpose_started, op=MPI.MAX)
    )
    local_dense_scalar_entries = 0
    local_max_interior = 0
    local_max_trace_rows = 0
    local_max_trace_columns = 0
    local_solve_seconds = 0.0
    local_insert_seconds = 0.0
    for interior in cells:
        (
            A_ii,
            A_it,
            A_ti,
            b_i,
            trace_original_rows,
            trace_original_columns,
        ) = _dense_cell_blocks(A, A_transpose, b, interior)
        solve_started = perf_counter()
        solved = np.linalg.solve(
            A_ii,
            np.column_stack((A_it, b_i)),
        )
        correction = A_ti @ solved[:, : A_it.shape[1]]
        rhs_correction = A_ti @ solved[:, -1]
        local_solve_seconds += perf_counter() - solve_started
        local_dense_scalar_entries += int(
            A_ii.size + A_it.size + A_ti.size + correction.size
        )
        local_max_interior = max(local_max_interior, len(interior))
        local_max_trace_rows = max(local_max_trace_rows, len(trace_original_rows))
        local_max_trace_columns = max(
            local_max_trace_columns, len(trace_original_columns)
        )
        trace_rows_mapped = _idx(
            mapping[int(value)] for value in trace_original_rows
        )
        trace_columns_mapped = _idx(
            mapping[int(value)] for value in trace_original_columns
        )
        insert_started = perf_counter()
        if correction.size:
            condensed.setValues(
                trace_rows_mapped,
                trace_columns_mapped,
                -np.asarray(correction, dtype=PETSc.ScalarType),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
        if len(rhs_correction):
            condensed_rhs.setValues(
                trace_rows_mapped,
                -np.asarray(rhs_correction, dtype=PETSc.ScalarType),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
        local_insert_seconds += perf_counter() - insert_started

    A_transpose.destroy()
    assemble_started = perf_counter()
    condensed.assemble()
    condensed_rhs.assemble()
    assemble_seconds = float(
        comm.allreduce(perf_counter() - assemble_started, op=MPI.MAX)
    )
    build_seconds = float(comm.allreduce(perf_counter() - started, op=MPI.MAX))
    audit = {
        "schema_version": "task035b.cell-static-condensation-build.v1",
        "status": "explicit_trace_schur_built",
        "full_rows": full_rows,
        "trace_rows": trace_rows,
        "interior_rows": interior_rows,
        "physical_row_compression_factor": float(full_rows / trace_rows),
        "owned_cell_count_global": int(
            comm.allreduce(len(cells), op=MPI.SUM)
        ),
        "maximum_cell_interior_rows": int(
            comm.allreduce(local_max_interior, op=MPI.MAX)
        ),
        "maximum_cell_trace_rows": int(
            comm.allreduce(local_max_trace_rows, op=MPI.MAX)
        ),
        "maximum_cell_trace_columns": int(
            comm.allreduce(local_max_trace_columns, op=MPI.MAX)
        ),
        "dense_scalar_entries_processed_sum": int(
            comm.allreduce(local_dense_scalar_entries, op=MPI.SUM)
        ),
        "all_cell_dense_factor_cache_retained": False,
        "full_matrix_required_as_input": True,
        "assembly_cost_avoided": False,
        "transpose_seconds": transpose_seconds,
        "local_dense_solve_seconds_max": float(
            comm.allreduce(local_solve_seconds, op=MPI.MAX)
        ),
        "schur_insert_seconds_max": float(
            comm.allreduce(local_insert_seconds, op=MPI.MAX)
        ),
        "final_assembly_seconds": assemble_seconds,
        "total_build_seconds": build_seconds,
    }
    return CellStaticCondensationSystem(
        matrix=condensed,
        rhs=condensed_rhs,
        owned_trace_original_dofs=owned_trace,
        original_to_trace=mapping,
        owned_cell_interiors=cells,
        full_rows=full_rows,
        trace_rows=trace_rows,
        interior_rows=interior_rows,
        build_audit=audit,
    )


def recover_full_solution(
    A: PETSc.Mat,
    b: PETSc.Vec,
    condensed: CellStaticCondensationSystem,
    trace_solution: PETSc.Vec,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Recover cell-interior values without retaining all local factors."""

    if trace_solution.getSize() != condensed.trace_rows:
        raise ValueError("trace solution size does not match condensed system")
    comm = A.getComm().tompi4py()
    started = perf_counter()
    trace_packets = comm.allgather(
        np.asarray(trace_solution.getArray(readonly=True), dtype=np.complex128).copy()
    )
    trace_values = np.concatenate(trace_packets)
    full = b.duplicate()
    full.set(PETSc.ScalarType(0.0))
    if len(condensed.owned_trace_original_dofs):
        full.setValues(
            condensed.owned_trace_original_dofs,
            np.asarray(trace_solution.getArray(readonly=True), dtype=PETSc.ScalarType),
        )

    local_solve_seconds = 0.0
    local_recovered = 0
    for interior in condensed.owned_cell_interiors:
        interior_set = set(int(value) for value in interior)
        trace_original_columns = _row_trace_columns(A, interior, interior_set)
        A_ii = np.asarray(
            A.getValues(interior, interior), dtype=np.complex128
        )
        A_it = np.asarray(
            A.getValues(interior, trace_original_columns), dtype=np.complex128
        )
        b_i = np.asarray(b.getValues(interior), dtype=np.complex128)
        trace_indices = _idx(
            condensed.original_to_trace[int(value)]
            for value in trace_original_columns
        )
        solve_started = perf_counter()
        interior_values = np.linalg.solve(
            A_ii,
            b_i - A_it @ trace_values[trace_indices],
        )
        local_solve_seconds += perf_counter() - solve_started
        local_recovered += len(interior)
        full.setValues(interior, np.asarray(interior_values, dtype=PETSc.ScalarType))
    full.assemble()
    return full, {
        "schema_version": "task035b.cell-static-condensation-recovery.v1",
        "status": "full_solution_recovered",
        "recovered_interior_rows": int(
            comm.allreduce(local_recovered, op=MPI.SUM)
        ),
        "all_cell_dense_factor_cache_retained": False,
        "local_dense_solve_seconds_max": float(
            comm.allreduce(local_solve_seconds, op=MPI.MAX)
        ),
        "total_recovery_seconds": float(
            comm.allreduce(perf_counter() - started, op=MPI.MAX)
        ),
    }


__all__ = [
    "CellStaticCondensationSystem",
    "build_explicit_cell_static_condensation",
    "owned_hcurl_cell_interior_dofs",
    "recover_full_solution",
]
