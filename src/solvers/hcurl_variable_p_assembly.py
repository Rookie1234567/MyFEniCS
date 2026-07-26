"""PETSc trace assembly for inactive-row-free Task035d variable-p cells."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from time import perf_counter
from typing import Any, Sequence

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
    _distributed_trace_preallocation,
)
from .hcurl_variable_p_local import project_p6_local_tensor


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
    periodic_constraints: VariablePPeriodicConstraintMap | None
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

    def destroy(self) -> None:
        self.matrix.destroy()

    def recover_owned_active_cells(
        self,
        trace_values: np.ndarray,
        *,
        active_full_rhs: PETSc.Vec | None = None,
    ) -> tuple[tuple[VariablePCellDofMap, np.ndarray], ...]:
        """Recover active local coefficients for each locally owned cell."""

        trace = np.asarray(trace_values, dtype=np.complex128)
        expected_trace_rows = int(self.matrix.getSize()[0])
        if trace.shape != (expected_trace_rows,):
            raise ValueError("global active trace vector has the wrong size")
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
            if self.periodic_constraints is None:
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
                interior += lu_solve(
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


def build_variable_p_condensed_trace_system(
    entity_map: VariablePGlobalEntityMap,
    p6_tensors_by_owned_cell: Sequence[np.ndarray],
    *,
    tensor_class_keys: Sequence[Any] | None = None,
    periodic_constraints: VariablePPeriodicConstraintMap | None = None,
) -> VariablePCondensedTraceSystem:
    """Project p6 cell tensors, condense interiors, and assemble active rows."""

    comm = entity_map.mesh.comm
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
    if (
        periodic_constraints is not None
        and periodic_constraints.entity_map is not entity_map
    ):
        raise ValueError(
            "periodic constraints must be built from the same entity map"
        )
    periodic_cells = (
        periodic_constraints.owned_cells
        if periodic_constraints is not None
        else (None,) * len(cells)
    )
    if len(periodic_cells) != len(cells):
        raise RuntimeError(
            "periodic constraints do not cover all locally owned cells"
        )
    for cell, periodic_cell in zip(
        cells,
        periodic_cells,
        strict=True,
    ):
        if (
            periodic_cell is not None
            and periodic_cell.global_cell != cell.global_cell
        ):
            raise RuntimeError(
                "periodic cell constraints differ from entity-map order"
            )

    started = perf_counter()
    active_rows = (
        periodic_constraints.independent_trace_rows
        if periodic_constraints is not None
        else entity_map.active_trace_rows
    )
    insertion_rows = tuple(
        periodic_cell.independent_rows
        if periodic_cell is not None
        else cell.trace_rows
        for cell, periodic_cell in zip(
            cells,
            periodic_cells,
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
            appended_global_rows=0,
            appended_support_owned_cell_groups=(),
            appended_support_group_by_row=(),
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
            (active_counts[comm.rank], active_rows),
            (active_counts[comm.rank], active_rows),
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
    for cell, p6_tensor, raw_key, periodic_cell in zip(
        cells,
        tensors,
        raw_keys,
        periodic_cells,
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
            schur = np.ascontiguousarray(A_tt + A_ti @ recovery)
            condensation_seconds += perf_counter() - condensation_started
            schur_cache[class_key] = schur
            interior_from_trace[class_key] = recovery
            interior_lu[class_key] = factor
            trace_from_interior_rhs[class_key] = trace_rhs
        insertion_started = perf_counter()
        if periodic_cell is None:
            rows = cell.trace_rows
            insertion_tensor = schur
        else:
            expansion = periodic_cell.full_trace_from_independent
            rows = periodic_cell.independent_rows
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
    actual_nnz = int(round(float(info.get("nz_used", 0.0))))
    if (
        matrix_rows != active_rows
        or matrix_columns != active_rows
        or actual_nnz != expected_nnz
    ):
        matrix.destroy()
        raise RuntimeError(
            "variable-p PETSc matrix does not match the exact active graph"
        )
    global_cells = int(comm.allreduce(len(cells), op=MPI.SUM))
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
        "active_trace_rows": active_rows,
        "periodic_slave_rows": int(
            entity_map.active_trace_rows - active_rows
        ),
        "floquet_elimination_applied_before_insertion": (
            periodic_constraints is not None
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
        "matrix_nnz_allocated": int(
            round(float(info.get("nz_allocated", 0.0)))
        ),
        "matrix_mallocs": int(
            round(float(info.get("mallocs", 0.0)))
        ),
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
        "final_assembly_seconds": assembly_seconds,
        "preallocation_seconds": preallocation_seconds,
        "total_build_seconds": float(
            comm.allreduce(perf_counter() - started, op=MPI.MAX)
        ),
        "trace_preallocation": preallocation,
        "full_p6_global_matrix_constructed": False,
        "full_active_global_matrix_constructed": False,
        "inactive_p6_rows_globally_numbered": False,
        "periodic_slave_rows_globally_numbered": False,
        "cell_p6_tensors_are_local_only": True,
        "ordinary_default_changed": False,
    }
    return VariablePCondensedTraceSystem(
        matrix=matrix,
        entity_map=entity_map,
        periodic_constraints=periodic_constraints,
        cell_recovery=tuple(recoveries),
        interior_from_trace_by_class=interior_from_trace,
        interior_lu_by_class=interior_lu,
        trace_from_interior_rhs_by_class=trace_from_interior_rhs,
        build_audit=audit,
    )


__all__ = [
    "VariablePCellRecovery",
    "VariablePCondensedTraceSystem",
    "build_variable_p_condensed_trace_system",
]
