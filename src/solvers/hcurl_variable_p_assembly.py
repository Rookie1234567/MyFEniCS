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
    _canonical_axis_aligned_coordinates,
    _cell_integral_kernels,
    _cell_tag_array,
    _distributed_trace_preallocation,
    _global_raw_tensor_cache,
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
        expected_trace_rows = self.active_trace_rows
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
    matrix_rows = active_rows + appended_global_rows
    local_appended = (
        appended_global_rows if comm.rank == comm.size - 1 else 0
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
        "appended_rows": appended_global_rows,
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
        "cell_p6_tensors_are_local_only": True,
        "ordinary_default_changed": False,
    }
    return VariablePCondensedTraceSystem(
        matrix=matrix,
        entity_map=entity_map,
        periodic_constraints=periodic_constraints,
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
    appended_global_rows: int = 0,
    appended_support_owned_cell_groups: tuple[np.ndarray, ...] = (),
    appended_support_group_by_row: tuple[int, ...] = (),
    defer_final_assembly: bool = False,
    geometry_tolerance: float = 1.0e-11,
) -> VariablePCondensedTraceSystem:
    """Evaluate p6 FFCx tensor classes and assemble the true active system."""

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
        for block in constraints.entity_blocks.values():
            if not (
                row_start <= int(block.full_rows[0]) < row_end
            ):
                continue
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
        for block in system.periodic_constraints.entity_blocks.values():
            if not (
                row_start <= int(block.full_rows[0]) < row_end
            ):
                continue
            values = (
                block.full_from_independent
                @ trace[block.independent_rows]
            )
            recovered.setValues(
                np.asarray(block.full_rows, dtype=PETSc.IntType),
                np.asarray(values, dtype=PETSc.ScalarType),
                addv=PETSc.InsertMode.INSERT_VALUES,
            )
    for cell, local_active in system.recover_owned_active_cells(
        trace,
        active_full_rhs=active_full_rhs,
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
