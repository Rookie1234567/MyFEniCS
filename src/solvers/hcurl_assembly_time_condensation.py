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
from time import perf_counter
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy import sparse


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
    """Physically reduced trace matrix and matrix-free recovery metadata."""

    matrix: PETSc.Mat
    owned_trace_original_dofs: np.ndarray
    original_to_trace: dict[int, int]
    trace_constraints: TraceConstraintMap
    cell_recovery_maps: tuple[CellRecoveryMap, ...]
    interior_from_trace_by_class: dict[tuple[Any, ...], np.ndarray]
    interior_inverse_by_class: dict[tuple[Any, ...], np.ndarray]
    trace_from_interior_rhs_by_class: dict[tuple[Any, ...], np.ndarray]
    full_rows: int
    trace_rows: int
    active_rows: int
    appended_rows: int
    interior_rows: int
    build_audit: dict[str, Any]

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


def _orient_cell_tensor(element, tensor: np.ndarray, cell_info: np.ndarray) -> None:
    """Apply the same ``T A T^T`` transformation as DOLFINx assembly."""

    dimension = tensor.shape[0]
    element.T_apply(tensor.ravel(), cell_info, dimension)
    transpose = np.ascontiguousarray(tensor.T)
    element.T_apply(transpose.ravel(), cell_info, dimension)
    tensor[:] = transpose.T


def build_unconstrained_assembly_time_condensation(
    compiled_form,
    function_space,
    cell_tags,
    *,
    mpc=None,
    appended_global_rows: int = 0,
    geometry_tolerance: float = 1.0e-11,
) -> AssemblyTimeCondensedSystem:
    """Assemble only the independent H(curl) trace Schur matrix.

    When ``mpc`` is supplied, its trace constraints are applied to each local
    Schur tensor before insertion.  No full-trace matrix or embedded slave
    identity rows are allocated.
    """

    if np.dtype(compiled_form.dtype) != np.dtype(np.complex128):
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
    active_start = int(sum(comm.allgather(len(owned_active))[: comm.rank]))
    local_appended = appended_global_rows if comm.rank == comm.size - 1 else 0
    matrix_rows = active_rows + appended_global_rows
    initial_nnz = min(
        matrix_rows,
        max(32, int(2 * len(trace_positions))),
    )
    condensed = PETSc.Mat().createAIJ(
        size=(
            (len(owned_active) + local_appended, matrix_rows),
            (len(owned_active) + local_appended, matrix_rows),
        ),
        nnz=initial_nnz,
        comm=comm,
    )
    if condensed.getOwnershipRange()[0] != active_start:
        condensed.destroy()
        raise RuntimeError(
            "PETSc active-trace ownership disagrees with trace numbering"
        )
    condensed.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)

    mesh.topology.create_entity_permutations()
    cell_permutations = mesh.topology.get_cell_permutation_info()
    raw_cache: dict[tuple[Any, ...], np.ndarray] = {}
    schur_cache: dict[tuple[Any, ...], np.ndarray] = {}
    recovery_cache: dict[tuple[Any, ...], np.ndarray] = {}
    inverse_cache: dict[tuple[Any, ...], np.ndarray] = {}
    rhs_trace_cache: dict[tuple[Any, ...], np.ndarray] = {}
    recovery_maps: list[CellRecoveryMap] = []
    local_kernel_seconds = 0.0
    local_schur_seconds = 0.0
    local_insert_seconds = 0.0
    for cell, original_dofs in enumerate(local_cell_dofs):
        canonical_coordinates, widths = _canonical_axis_aligned_coordinates(
            mesh,
            cell,
            tolerance=geometry_tolerance,
        )
        tag = int(tags[cell])
        raw_key = (tag, *widths)
        tensor = raw_cache.get(raw_key)
        if tensor is None:
            kernel_started = perf_counter()
            tensor = np.zeros((dimension, dimension), dtype=np.complex128)
            default_kernel = kernels.get(-1)
            if default_kernel is not None:
                tensor += _tabulate_cell_tensor(
                    compiled_form,
                    default_kernel,
                    canonical_coordinates,
                    dimension,
                )
            tagged_kernel = kernels.get(tag)
            if tagged_kernel is not None:
                tensor += _tabulate_cell_tensor(
                    compiled_form,
                    tagged_kernel,
                    canonical_coordinates,
                    dimension,
                )
            if default_kernel is None and tagged_kernel is None:
                condensed.destroy()
                raise ValueError(
                    f"compiled form has no default or tagged kernel for tag {tag}"
                )
            local_kernel_seconds += perf_counter() - kernel_started
            raw_cache[raw_key] = tensor
        class_key = (*raw_key, int(cell_permutations[cell]))
        schur = schur_cache.get(class_key)
        if schur is None:
            schur_started = perf_counter()
            oriented = tensor.copy()
            _orient_cell_tensor(
                element,
                oriented,
                np.asarray(cell_permutations[cell : cell + 1], dtype=np.uint32),
            )
            A_ii = oriented[np.ix_(interior_positions, interior_positions)]
            A_it = oriented[np.ix_(interior_positions, trace_positions)]
            A_ti = oriented[np.ix_(trace_positions, interior_positions)]
            A_tt = oriented[np.ix_(trace_positions, trace_positions)]
            interior_from_trace = -np.linalg.solve(A_ii, A_it)
            interior_inverse = np.linalg.solve(
                A_ii,
                np.eye(len(interior_positions), dtype=np.complex128),
            )
            trace_from_interior_rhs = -(A_ti @ interior_inverse)
            schur = A_tt + A_ti @ interior_from_trace
            local_schur_seconds += perf_counter() - schur_started
            schur_cache[class_key] = schur
            recovery_cache[class_key] = interior_from_trace
            inverse_cache[class_key] = interior_inverse
            rhs_trace_cache[class_key] = trace_from_interior_rhs
        trace_original = original_dofs[trace_positions]
        active_ids, local_expansion, identity_expansion = (
            _cell_trace_expansion(
                trace_original,
                trace_constraints,
            )
        )
        active_schur = _constrain_local_schur(
            schur,
            local_expansion,
            identity_expansion,
        )
        insert_started = perf_counter()
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
    assembly_started = perf_counter()
    condensed.assemble()
    final_assembly_seconds = float(
        comm.allreduce(perf_counter() - assembly_started, op=MPI.MAX)
    )
    interior_rows = full_rows - trace_rows
    global_cells = int(comm.allreduce(owned_cells, op=MPI.SUM))
    raw_class_count = int(comm.allreduce(len(raw_cache), op=MPI.SUM))
    oriented_class_count = int(comm.allreduce(len(schur_cache), op=MPI.SUM))
    return AssemblyTimeCondensedSystem(
        matrix=condensed,
        owned_trace_original_dofs=owned_trace,
        original_to_trace=mapping,
        trace_constraints=trace_constraints,
        cell_recovery_maps=tuple(recovery_maps),
        interior_from_trace_by_class=recovery_cache,
        interior_inverse_by_class=inverse_cache,
        trace_from_interior_rhs_by_class=rhs_trace_cache,
        full_rows=full_rows,
        trace_rows=trace_rows,
        active_rows=active_rows,
        appended_rows=appended_global_rows,
        interior_rows=interior_rows,
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
            "full_global_matrix_allocated": False,
            "full_trace_matrix_allocated": False,
            "embedded_mpc_slave_identity_rows_allocated": False,
            "assembly_cost_avoided": True,
            "axis_aligned_affine_geometry_verified": True,
            "raw_tensor_class_count_sum": raw_class_count,
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
            "local_insert_seconds_max": float(
                comm.allreduce(local_insert_seconds, op=MPI.MAX)
            ),
            "final_assembly_seconds": final_assembly_seconds,
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
        local += np.vdot(
            left_values,
            condensed.interior_inverse_by_class[cell.class_key]
            @ right_values,
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
                + condensed.interior_inverse_by_class[cell.class_key]
                @ rhs_values[rows - rhs_start]
            )
        result.append((cell.interior_original_dofs, values))
    return tuple(result)


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
    "build_unconstrained_assembly_time_condensation",
    "cell_interior_schur_bilinear",
    "condense_unconstrained_vector_to_active_trace",
    "project_mpc_vector_to_active_trace",
    "recover_owned_cell_interiors",
]
