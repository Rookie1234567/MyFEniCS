"""Research-only strong trace-subspace Hybrid direct solver.

The historical Hybrid formulation constrains only the modal projection of
the internal finite-element trace.  This module instead restricts the trial
trace itself to the physical right-modal subspace and replaces the removed
finite-element interface rows by normalized left-modal Petrov rows.

Only rectangular ``N_gamma x M``, ``M x N_gamma`` and small ``M x M``
objects are formed.  In particular, no ``R D`` interface projector, penalty,
or full-dimensional multiplier is constructed.

The only qualified claim is complete tangential-electric-trace continuity.
Joint-Cauchy continuity, all diffraction channels, and Hybrid-P production
use remain unqualified.  Every construction entry point requires an explicit
``research_opt_in=True`` argument and no ordinary solver default imports this
module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Callable, Iterable

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from ..coupling.hybrid_internal_modes import (
    HybridInternalModeCoupling,
    _ReusableInterfaceLifter,
)
from .common_3d_solve import _petsc_matrix_stats
from .hybrid_local_dtn import HybridLocalDtnSystem


STRONG_TRACE_STATUS = "research_only"


def strong_trace_research_contract() -> dict[str, object]:
    """Return the fixed qualification boundary for this opt-in capability."""

    return {
        "status": STRONG_TRACE_STATUS,
        "qualified_claims": ("complete_tangential_e_continuity",),
        "unqualified_claims": (
            "joint_cauchy_continuity",
            "all_diffraction_channels",
            "hybrid_p_production",
        ),
        "hybrid_p_production_qualified": False,
    }


def _require_research_opt_in(research_opt_in: bool) -> None:
    if research_opt_in is not True:
        raise ValueError(
            "Strong-trace Hybrid is research_only; pass "
            "research_opt_in=True explicitly."
        )


def _owned_global_slave_rows(system: HybridLocalDtnSystem) -> np.ndarray:
    """Return globally unique owned Floquet slave rows in original numbering."""

    index_map = system.V.dofmap.index_map
    if int(system.V.dofmap.index_map_bs) != 1:
        raise NotImplementedError(
            "Strong trace currently requires scalar-blocked H(curl)."
        )
    local = np.unique(np.asarray(system.floquet_data.local_slave_dofs, dtype=np.int64))
    local = local[(local >= 0) & (local < int(index_map.size_local))]
    owned = np.asarray(
        index_map.local_to_global(local.astype(np.int32)),
        dtype=np.int64,
    )
    gathered = system.local_mesh.mesh.comm.allgather(owned)
    return np.asarray(
        sorted({int(value) for packet in gathered for value in packet}),
        dtype=PETSc.IntType,
    )


def _geometric_interface_original_rows(
    system: HybridLocalDtnSystem,
) -> tuple[np.ndarray, np.ndarray]:
    """Return all and locally owned original DoFs on the internal facet closure."""

    mesh = system.local_mesh.mesh
    facets = np.asarray(
        system.local_mesh.mesh_data.facet_tags.find(
            system.local_mesh.interface_facet_tag
        ),
        dtype=np.int32,
    )
    local_dofs = np.unique(
        np.asarray(
            fem.locate_dofs_topological(
                system.V,
                mesh.topology.dim - 1,
                facets,
                remote=True,
            ),
            dtype=np.int64,
        )
    )
    index_map = system.V.dofmap.index_map
    owned_local = local_dofs[
        (local_dofs >= 0) & (local_dofs < int(index_map.size_local))
    ]
    owned_original = np.asarray(
        index_map.local_to_global(owned_local.astype(np.int32)),
        dtype=np.int64,
    )
    packets = mesh.comm.allgather(owned_original)
    all_original = np.asarray(
        sorted({int(value) for packet in packets for value in packet}),
        dtype=PETSc.IntType,
    )
    return all_original, owned_original


def _projection_column_support(matrix: PETSc.Mat) -> np.ndarray:
    """Return the distributed union of explicitly stored projection columns."""

    first, last = matrix.getOwnershipRange()
    local: set[int] = set()
    for row in range(first, last):
        columns, values = matrix.getRow(row)
        local.update(
            int(column)
            for column, value in zip(columns, values, strict=True)
            if abs(complex(value)) > 0.0
        )
    packets = matrix.getComm().tompi4py().allgather(tuple(sorted(local)))
    return np.asarray(
        sorted({value for packet in packets for value in packet}),
        dtype=PETSc.IntType,
    )


def _small_matrix_to_numpy(matrix: PETSc.Mat) -> np.ndarray:
    """Replicate a small row-distributed PETSc matrix."""

    comm = matrix.getComm().tompi4py()
    rows, columns = map(int, matrix.getSize())
    owner = comm.size - 1
    local = None
    first, last = matrix.getOwnershipRange()
    if first == 0 and last == rows:
        local = np.asarray(
            matrix.getValues(
                np.arange(rows, dtype=PETSc.IntType),
                np.arange(columns, dtype=PETSc.IntType),
            ),
            dtype=np.complex128,
        )
        owner = comm.rank
    owners = comm.allgather(owner if local is not None else -1)
    actual = max(owners)
    if actual < 0:
        raise RuntimeError("No rank owns the small matrix rows.")
    return np.asarray(comm.bcast(local, root=actual), dtype=np.complex128)


def _small_vector_to_numpy(vector: PETSc.Vec) -> np.ndarray:
    comm = vector.getComm().tompi4py()
    size = int(vector.getSize())
    first, last = vector.getOwnershipRange()
    local = None
    owner = -1
    if first == 0 and last == size:
        local = np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
        owner = comm.rank
    actual = max(comm.allgather(owner))
    if actual < 0:
        raise RuntimeError("No rank owns the small vector.")
    return np.asarray(comm.bcast(local, root=actual), dtype=np.complex128)


def _create_rectangular_aij(
    comm: MPI.Intracomm,
    *,
    global_rows: int,
    local_rows: int,
    global_cols: int,
    local_cols: int,
) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        size=((local_rows, global_rows), (local_cols, global_cols)),
        comm=comm,
    )
    matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    return matrix


@dataclass
class HybridStrongTraceInterfaceMap:
    """Backend-native independent interface rows and physical prolongation."""

    side: str
    interface_rows: np.ndarray
    retained_rows_by_rank: tuple[np.ndarray, ...]
    removed_slave_rows: np.ndarray
    right_prolongation: PETSc.Mat
    petrov_left_columns: PETSc.Mat
    projection_identity_error: float
    geometry_projection_support_match: bool
    lifted_query_points: int
    original_interface_rows: int
    trace_complement_unknown_count: int = 0
    dense_interface_square_formed: bool = False
    research_only: bool = True
    _destroyed: bool = field(default=False, init=False, repr=False)

    @property
    def retained_rows(self) -> np.ndarray:
        return np.concatenate(self.retained_rows_by_rank).astype(
            PETSc.IntType, copy=False
        )

    def destroy(self) -> None:
        if not self._destroyed:
            self.petrov_left_columns.destroy()
            self.right_prolongation.destroy()
            self._destroyed = True


def build_hybrid_strong_trace_interface_map(
    system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
    *,
    research_opt_in: bool = False,
) -> HybridStrongTraceInterfaceMap:
    """Build ``R_s`` and exact backend row sets, failing closed on mismatch."""

    _require_research_opt_in(research_opt_in)

    block = coupling.bottom if system.side == "bottom" else coupling.top
    projection = block.projection
    mode_count = coupling.mode_count_per_direction
    if projection.getSize() != (mode_count, system.global_size):
        raise ValueError("Hybrid projection and local system shapes disagree.")

    original_interface, owned_original_interface = _geometric_interface_original_rows(
        system
    )
    slave_rows = _owned_global_slave_rows(system)
    slave_set = {int(value) for value in slave_rows}

    if system.static_condensation is None:
        geometry_rows = np.asarray(
            sorted(
                int(value)
                for value in original_interface
                if int(value) not in slave_set
            ),
            dtype=PETSc.IntType,
        )
        owned_original_to_algebra = {
            int(value): int(value)
            for value in owned_original_interface
            if int(value) not in slave_set
        }
        removed_slaves = slave_rows
    else:
        constraints = system.static_condensation.condensed.trace_constraints
        geometry_active: set[int] = set()
        for original in original_interface:
            expansion = constraints.expansion_by_original.get(int(original))
            if expansion is None:
                raise RuntimeError(
                    "Internal interface contains a non-trace static row."
                )
            geometry_active.update(int(value) for value in expansion[0])
        geometry_rows = np.asarray(sorted(geometry_active), dtype=PETSc.IntType)
        original_interface_set = {int(value) for value in original_interface}
        owned_original_to_algebra = {
            int(original): int(constraints.original_to_active[int(original)])
            for original in constraints.owned_active_original_dofs
            if int(original) in original_interface_set
        }
        removed_slaves = np.empty(0, dtype=PETSc.IntType)

    mapped_packets = system.local_mesh.mesh.comm.allgather(
        tuple(sorted(owned_original_to_algebra.values()))
    )
    mapped_rows = {int(value) for packet in mapped_packets for value in packet}
    expected_geometry_rows = set(map(int, geometry_rows))
    if mapped_rows != expected_geometry_rows or sum(map(len, mapped_packets)) != len(
        expected_geometry_rows
    ):
        missing_mapped = sorted(expected_geometry_rows - mapped_rows)
        extra_mapped = sorted(mapped_rows - expected_geometry_rows)
        raise RuntimeError(
            f"{system.side} strong-trace original/algebra row map does not "
            f"close: missing={missing_mapped[:8]}, "
            f"extra={extra_mapped[:8]}."
        )

    projection_rows = _projection_column_support(projection)
    missing = sorted(set(map(int, geometry_rows)) - set(map(int, projection_rows)))
    extra = sorted(set(map(int, projection_rows)) - set(map(int, geometry_rows)))
    if extra:
        raise RuntimeError(
            f"{system.side} strong-trace geometry/projection row mismatch: "
            f"missing={missing[:8]}, extra={extra[:8]}."
        )
    if np.any(geometry_rows >= system.n_fe):
        raise RuntimeError(
            "Internal projection unexpectedly touches external auxiliary rows."
        )

    # Every independent DoF on the internal facet belongs to the strong trial
    # restriction, including rows on which a deliberately tiny synthetic
    # modal fixture happens to vanish.  Formal high-order anchors additionally
    # require the projection support to cover this complete geometric set.
    interface_rows = geometry_rows
    removed = set(map(int, interface_rows)) | set(map(int, removed_slaves))
    first, last = system.A.getOwnershipRange()
    local_retained = np.asarray(
        [row for row in range(first, last) if row not in removed],
        dtype=PETSc.IntType,
    )
    retained_by_rank = tuple(
        np.asarray(packet, dtype=PETSc.IntType)
        for packet in system.local_mesh.mesh.comm.allgather(local_retained)
    )
    retained_union = set(int(value) for packet in retained_by_rank for value in packet)
    if retained_union & removed:
        raise RuntimeError("Strong-trace retained and removed row sets overlap.")
    if len(retained_union) + len(removed) != system.global_size:
        raise RuntimeError(
            "Strong-trace retained/removed row accounting does not close."
        )
    expected_aux = set(range(system.n_fe, system.global_size))
    if not expected_aux.issubset(retained_union):
        raise RuntimeError(
            "Strong-trace row map removed an external DtN auxiliary row."
        )

    comm = system.local_mesh.mesh.comm
    local_mode_columns = mode_count if comm.rank == comm.size - 1 else 0
    prolongation = _create_rectangular_aij(
        comm,
        global_rows=system.global_size,
        local_rows=system.A.getLocalSize()[0],
        global_cols=mode_count,
        local_cols=local_mode_columns,
    )
    petrov_columns = _create_rectangular_aij(
        comm,
        global_rows=system.global_size,
        local_rows=system.A.getLocalSize()[0],
        global_cols=mode_count,
        local_cols=local_mode_columns,
    )
    lifter = _ReusableInterfaceLifter(system, target_space=system.V)
    lifted_queries = 0
    try:
        original_rows = np.asarray(
            sorted(owned_original_to_algebra), dtype=PETSc.IntType
        )
        algebra_rows = np.asarray(
            [owned_original_to_algebra[int(value)] for value in original_rows],
            dtype=PETSc.IntType,
        )
        for column, trace in enumerate(coupling.projection.right_traces):
            field, queries = lifter.lift(trace)
            lifted_queries += int(queries)
            system.floquet_data.mpc.homogenize(field)
            field.x.scatter_forward()
            # ``petsc_vec`` lazily creates a distributed PETSc wrapper and is
            # therefore collective.  Create it on every rank even when this
            # rank owns no interface rows; otherwise a small MPI fixture with
            # empty interface partitions deadlocks here.
            field_vector = field.x.petsc_vec
            values = (
                np.asarray(
                    field_vector.getValues(original_rows),
                    dtype=PETSc.ScalarType,
                )
                if len(original_rows)
                else np.empty(0, dtype=PETSc.ScalarType)
            )
            nonzero = np.abs(values) > 0.0
            if np.any(nonzero):
                prolongation.setValues(
                    algebra_rows[nonzero],
                    np.asarray([column], dtype=PETSc.IntType),
                    values[nonzero].reshape((-1, 1)),
                    addv=PETSc.InsertMode.INSERT_VALUES,
                )
        prolongation.assemble()

        raw_left = np.empty((len(original_rows), mode_count), dtype=np.complex128)
        for column, trace in enumerate(coupling.projection.left_traces):
            field, queries = lifter.lift(trace)
            lifted_queries += int(queries)
            system.floquet_data.mpc.homogenize(field)
            field.x.scatter_forward()
            field_vector = field.x.petsc_vec
            raw_left[:, column] = (
                np.asarray(
                    field_vector.getValues(original_rows),
                    dtype=np.complex128,
                )
                if len(original_rows)
                else np.empty(0, dtype=np.complex128)
            )
        inverse_gram = np.asarray(block.inverse_trace_gram, dtype=np.complex128)
        if inverse_gram.shape != (mode_count, mode_count):
            raise RuntimeError("Strong-trace inverse surface Gram has the wrong shape.")
        normalized_left = raw_left @ inverse_gram.conj().T
        if not np.all(np.isfinite(normalized_left)):
            raise RuntimeError("Strong-trace normalized left columns are non-finite.")
        for column in range(mode_count):
            values = normalized_left[:, column]
            nonzero = np.abs(values) > 0.0
            if np.any(nonzero):
                petrov_columns.setValues(
                    algebra_rows[nonzero],
                    np.asarray([column], dtype=PETSc.IntType),
                    np.asarray(values[nonzero], dtype=PETSc.ScalarType).reshape(
                        (-1, 1)
                    ),
                    addv=PETSc.InsertMode.INSERT_VALUES,
                )
        petrov_columns.assemble()

        identity_matrix = projection.matMult(prolongation)
        try:
            identity = _small_matrix_to_numpy(identity_matrix)
        finally:
            identity_matrix.destroy()
        identity_error = float(
            np.linalg.norm(identity - np.eye(mode_count), ord=np.inf)
        )
        if (
            not np.all(np.isfinite(identity))
            or identity_error > 1.0e-10
            or np.linalg.matrix_rank(identity) != mode_count
        ):
            raise RuntimeError(
                f"{system.side} strong trace D*R identity failed: "
                f"error={identity_error:.3e}."
            )
    except Exception:
        petrov_columns.destroy()
        prolongation.destroy()
        raise

    return HybridStrongTraceInterfaceMap(
        side=system.side,
        interface_rows=interface_rows,
        retained_rows_by_rank=retained_by_rank,
        removed_slave_rows=removed_slaves,
        right_prolongation=prolongation,
        petrov_left_columns=petrov_columns,
        projection_identity_error=identity_error,
        geometry_projection_support_match=not missing,
        lifted_query_points=lifted_queries,
        original_interface_rows=int(len(original_interface)),
    )


@dataclass(frozen=True)
class HybridStrongTraceLayout:
    """Rank-major layout for retained local rows and the two modal directions."""

    comm: MPI.Intracomm
    bottom_retained_by_rank: tuple[np.ndarray, ...]
    top_retained_by_rank: tuple[np.ndarray, ...]
    combined_offsets: tuple[int, ...]
    modal_count: int
    modal_owner: int
    bottom_old_to_new: dict[int, int]
    top_old_to_new: dict[int, int]

    @classmethod
    def build(
        cls,
        bottom: HybridStrongTraceInterfaceMap,
        top: HybridStrongTraceInterfaceMap,
        modal_count: int,
        comm: MPI.Intracomm,
    ) -> HybridStrongTraceLayout:
        bottom_sizes = tuple(len(rows) for rows in bottom.retained_rows_by_rank)
        top_sizes = tuple(len(rows) for rows in top.retained_rows_by_rank)
        modal_owner = comm.size - 1
        local_sizes = tuple(
            bottom_sizes[rank]
            + top_sizes[rank]
            + (modal_count if rank == modal_owner else 0)
            for rank in range(comm.size)
        )
        offsets: list[int] = []
        running = 0
        for size in local_sizes:
            offsets.append(running)
            running += size
        bottom_map: dict[int, int] = {}
        top_map: dict[int, int] = {}
        for rank in range(comm.size):
            rank_offset = offsets[rank]
            bottom_map.update(
                (int(old), rank_offset + position)
                for position, old in enumerate(bottom.retained_rows_by_rank[rank])
            )
            top_offset = rank_offset + bottom_sizes[rank]
            top_map.update(
                (int(old), top_offset + position)
                for position, old in enumerate(top.retained_rows_by_rank[rank])
            )
        if len(bottom_map) != sum(bottom_sizes) or len(top_map) != sum(top_sizes):
            raise RuntimeError("Strong-trace retained row numbering is not unique.")
        return cls(
            comm=comm,
            bottom_retained_by_rank=bottom.retained_rows_by_rank,
            top_retained_by_rank=top.retained_rows_by_rank,
            combined_offsets=tuple(offsets),
            modal_count=int(modal_count),
            modal_owner=modal_owner,
            bottom_old_to_new=bottom_map,
            top_old_to_new=top_map,
        )

    @property
    def bottom_sizes(self) -> tuple[int, ...]:
        return tuple(len(rows) for rows in self.bottom_retained_by_rank)

    @property
    def top_sizes(self) -> tuple[int, ...]:
        return tuple(len(rows) for rows in self.top_retained_by_rank)

    @property
    def global_size(self) -> int:
        return int(sum(self.bottom_sizes) + sum(self.top_sizes) + self.modal_count)

    @property
    def local_size(self) -> int:
        rank = self.comm.rank
        return int(
            self.bottom_sizes[rank]
            + self.top_sizes[rank]
            + (self.modal_count if rank == self.modal_owner else 0)
        )

    @property
    def modal_global_start(self) -> int:
        rank = self.modal_owner
        return int(
            self.combined_offsets[rank] + self.bottom_sizes[rank] + self.top_sizes[rank]
        )

    def map_bottom(self, indices: Iterable[int] | np.ndarray) -> np.ndarray:
        return np.asarray(
            [self.bottom_old_to_new[int(value)] for value in indices],
            dtype=PETSc.IntType,
        )

    def map_top(self, indices: Iterable[int] | np.ndarray) -> np.ndarray:
        return np.asarray(
            [self.top_old_to_new[int(value)] for value in indices],
            dtype=PETSc.IntType,
        )

    def map_modal(self, indices: Iterable[int] | np.ndarray) -> np.ndarray:
        values = np.asarray(tuple(indices), dtype=np.int64)
        if np.any(values < 0) or np.any(values >= self.modal_count):
            raise IndexError("Strong-trace modal index lies outside the layout.")
        return np.asarray(self.modal_global_start + values, dtype=PETSc.IntType)


def _dense_row(matrix: PETSc.Mat, row: int, width: int) -> np.ndarray:
    columns, values = matrix.getRow(int(row))
    result = np.zeros(width, dtype=np.complex128)
    if len(columns):
        result[np.asarray(columns, dtype=np.int64)] = np.asarray(
            values, dtype=np.complex128
        )
    return result


def _copy_retained_block(
    target: PETSc.Mat,
    source: PETSc.Mat,
    retained_local: np.ndarray,
    old_to_new: dict[int, int],
) -> int:
    inserted = 0
    for row in retained_local:
        columns, values = source.getRow(int(row))
        keep = np.asarray([int(column) in old_to_new for column in columns], dtype=bool)
        if not np.any(keep):
            continue
        kept_columns = np.asarray(columns, dtype=np.int64)[keep]
        target.setValues(
            np.asarray([old_to_new[int(row)]], dtype=PETSc.IntType),
            np.asarray(
                [old_to_new[int(column)] for column in kept_columns],
                dtype=PETSc.IntType,
            ),
            np.asarray(values, dtype=PETSc.ScalarType)[keep].reshape(1, -1),
            addv=PETSc.InsertMode.ADD_VALUES,
        )
        inserted += int(np.count_nonzero(keep))
    return inserted


def _side_modal_row(
    *,
    side: str,
    ar: np.ndarray,
    positive: np.ndarray,
    negative: np.ndarray,
    negative_map: np.ndarray,
    forward: np.ndarray,
    backward: np.ndarray,
) -> np.ndarray:
    if side == "bottom":
        return np.concatenate(
            (
                ar + positive,
                (ar @ negative_map + negative) * backward,
            )
        )
    if side == "top":
        return np.concatenate(
            (
                (ar + positive) * forward,
                ar @ negative_map + negative,
            )
        )
    raise ValueError(f"Unknown Hybrid side {side!r}.")


def _insert_retained_to_modal(
    target: PETSc.Mat,
    *,
    system: HybridLocalDtnSystem,
    interface_map: HybridStrongTraceInterfaceMap,
    layout_map: Callable[[Iterable[int] | np.ndarray], np.ndarray],
    modal_columns: np.ndarray,
    block: Any,
    side: str,
    negative_map: np.ndarray,
    forward: np.ndarray,
    backward: np.ndarray,
) -> tuple[int, PETSc.Mat]:
    ar = system.A.matMult(interface_map.right_prolongation)
    first, last = system.A.getOwnershipRange()
    retained_local = interface_map.retained_rows_by_rank[
        system.local_mesh.mesh.comm.rank
    ]
    inserted = 0
    try:
        for row in retained_local:
            values = _side_modal_row(
                side=side,
                ar=_dense_row(ar, int(row), len(forward)),
                positive=_dense_row(block.positive_traction, int(row), len(forward)),
                negative=_dense_row(block.negative_traction, int(row), len(forward)),
                negative_map=negative_map,
                forward=forward,
                backward=backward,
            )
            nonzero = np.abs(values) > 0.0
            if np.any(nonzero):
                target.setValues(
                    layout_map([int(row)]),
                    modal_columns[nonzero],
                    values[nonzero].reshape(1, -1),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
                inserted += int(np.count_nonzero(nonzero))
        if not (first <= int(retained_local[0]) if len(retained_local) else True):
            raise RuntimeError("Strong-trace retained rows violate PETSc ownership.")
        return inserted, ar
    except Exception:
        ar.destroy()
        raise


def _insert_petrov_rows(
    target: PETSc.Mat,
    rhs: PETSc.Vec,
    *,
    system: HybridLocalDtnSystem,
    interface_map: HybridStrongTraceInterfaceMap,
    block: Any,
    ar: PETSc.Mat,
    layout_map: Callable[[Iterable[int] | np.ndarray], np.ndarray],
    retained_old_to_new: dict[int, int],
    petrov_rows: np.ndarray,
    modal_columns: np.ndarray,
    side: str,
    negative_map: np.ndarray,
    forward: np.ndarray,
    backward: np.ndarray,
) -> dict[str, int]:
    petrov_h = None
    da = None
    dar_matrix = None
    dc_positive_matrix = None
    dc_negative_matrix = None
    projected_rhs = None
    inserted_retained = 0
    inserted_modal = 0
    try:
        petrov_h = PETSc.Mat()
        interface_map.petrov_left_columns.hermitianTranspose(petrov_h)
        da = petrov_h.matMult(system.A)
        dar_matrix = petrov_h.matMult(ar)
        dc_positive_matrix = petrov_h.matMult(block.positive_traction)
        dc_negative_matrix = petrov_h.matMult(block.negative_traction)
        projected_rhs = petrov_h.createVecLeft()
        petrov_h.mult(system.b, projected_rhs)
        dar = _small_matrix_to_numpy(dar_matrix)
        dc_positive = _small_matrix_to_numpy(dc_positive_matrix)
        dc_negative = _small_matrix_to_numpy(dc_negative_matrix)
        rhs_values = _small_vector_to_numpy(projected_rhs)
        first, last = da.getOwnershipRange()
        for mode_row in range(first, last):
            columns, values = da.getRow(mode_row)
            kept = [
                (int(column), complex(value))
                for column, value in zip(columns, values, strict=True)
                if int(column) in retained_old_to_new
            ]
            if kept:
                target.setValues(
                    np.asarray([petrov_rows[mode_row]], dtype=PETSc.IntType),
                    layout_map([column for column, _value in kept]),
                    np.asarray(
                        [value for _column, value in kept],
                        dtype=PETSc.ScalarType,
                    ).reshape(1, -1),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
                inserted_retained += len(kept)
            modal_values = _side_modal_row(
                side=side,
                ar=dar[mode_row],
                positive=dc_positive[mode_row],
                negative=dc_negative[mode_row],
                negative_map=negative_map,
                forward=forward,
                backward=backward,
            )
            nonzero = np.abs(modal_values) > 0.0
            if np.any(nonzero):
                target.setValues(
                    np.asarray([petrov_rows[mode_row]], dtype=PETSc.IntType),
                    modal_columns[nonzero],
                    modal_values[nonzero].reshape(1, -1),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
                inserted_modal += int(np.count_nonzero(nonzero))
            rhs.setValue(
                int(petrov_rows[mode_row]),
                PETSc.ScalarType(rhs_values[mode_row]),
                addv=PETSc.InsertMode.INSERT_VALUES,
            )
    finally:
        for temporary in (
            projected_rhs,
            dc_negative_matrix,
            dc_positive_matrix,
            dar_matrix,
            da,
            petrov_h,
        ):
            if temporary is not None:
                temporary.destroy()
    return {
        "petrov_to_retained": inserted_retained,
        "petrov_to_modal": inserted_modal,
    }


@dataclass
class HybridStrongTraceDirectSystem:
    A: PETSc.Mat
    b: PETSc.Vec
    layout: HybridStrongTraceLayout
    bottom_interface: HybridStrongTraceInterfaceMap
    top_interface: HybridStrongTraceInterfaceMap
    matrix_stats: dict[str, Any]
    block_shapes: dict[str, tuple[int, int]]
    inserted_nnz_by_block: dict[str, int]
    dense_interface_square_formed: bool = False
    old_modal_constraint_retained: bool = False
    research_only: bool = True
    hybrid_p_production_qualified: bool = False
    _destroyed: bool = field(default=False, init=False, repr=False)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.A.destroy()
        self.b.destroy()
        self.bottom_interface.destroy()
        self.top_interface.destroy()
        self._destroyed = True


def build_hybrid_strong_trace_direct_system(
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
    *,
    research_opt_in: bool = False,
) -> HybridStrongTraceDirectSystem:
    """Assemble the square Petrov--Galerkin strong-trace system."""

    _require_research_opt_in(research_opt_in)

    if bottom_system.side != "bottom" or top_system.side != "top":
        raise ValueError("Hybrid local systems must be ordered bottom, top.")
    if bottom_system.assembly_backend_actual != top_system.assembly_backend_actual:
        raise ValueError("Hybrid strong-trace bottom/top backends must match.")
    comm = bottom_system.local_mesh.mesh.comm
    mode_count = coupling.mode_count_per_direction
    internal_count = coupling.internal_unknown_count
    bottom_map = build_hybrid_strong_trace_interface_map(
        bottom_system,
        coupling,
        research_opt_in=True,
    )
    top_map = None
    matrix = None
    rhs = None
    bottom_ar = None
    top_ar = None
    try:
        top_map = build_hybrid_strong_trace_interface_map(
            top_system,
            coupling,
            research_opt_in=True,
        )
        layout = HybridStrongTraceLayout.build(
            bottom_map, top_map, internal_count, comm
        )
        matrix = PETSc.Mat().createAIJ(
            size=(
                (layout.local_size, layout.global_size),
                (layout.local_size, layout.global_size),
            ),
            comm=comm,
        )
        matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
        rhs = PETSc.Vec().createMPI((layout.local_size, layout.global_size), comm=comm)
        rhs.set(PETSc.ScalarType(0.0))
        rank = comm.rank
        inserted: dict[str, int] = {}
        inserted["A_bottom_retained"] = _copy_retained_block(
            matrix,
            bottom_system.A,
            bottom_map.retained_rows_by_rank[rank],
            layout.bottom_old_to_new,
        )
        inserted["A_top_retained"] = _copy_retained_block(
            matrix,
            top_system.A,
            top_map.retained_rows_by_rank[rank],
            layout.top_old_to_new,
        )

        for system, interface, map_rows in (
            (bottom_system, bottom_map, layout.map_bottom),
            (top_system, top_map, layout.map_top),
        ):
            retained = interface.retained_rows_by_rank[rank]
            if len(retained):
                target_rows = map_rows(retained)
                source_values = np.asarray(
                    system.b.getValues(retained), dtype=PETSc.ScalarType
                )
                rhs.setValues(
                    target_rows,
                    source_values,
                    addv=PETSc.InsertMode.INSERT_VALUES,
                )

        forward = np.asarray(coupling.propagation.forward.factors, dtype=np.complex128)
        backward = np.asarray(
            coupling.propagation.backward.factors, dtype=np.complex128
        )
        negative_map = np.asarray(
            coupling.negative_trace_to_positive, dtype=np.complex128
        )
        modal_columns = layout.map_modal(range(internal_count))
        bottom_inserted, bottom_ar = _insert_retained_to_modal(
            matrix,
            system=bottom_system,
            interface_map=bottom_map,
            layout_map=layout.map_bottom,
            modal_columns=modal_columns,
            block=coupling.bottom,
            side="bottom",
            negative_map=negative_map,
            forward=forward,
            backward=backward,
        )
        top_inserted, top_ar = _insert_retained_to_modal(
            matrix,
            system=top_system,
            interface_map=top_map,
            layout_map=layout.map_top,
            modal_columns=modal_columns,
            block=coupling.top,
            side="top",
            negative_map=negative_map,
            forward=forward,
            backward=backward,
        )
        inserted["bottom_retained_to_modal"] = bottom_inserted
        inserted["top_retained_to_modal"] = top_inserted
        petrov_rows = layout.map_modal(range(internal_count))
        try:
            bottom_petrov = _insert_petrov_rows(
                matrix,
                rhs,
                system=bottom_system,
                interface_map=bottom_map,
                block=coupling.bottom,
                ar=bottom_ar,
                layout_map=layout.map_bottom,
                retained_old_to_new=layout.bottom_old_to_new,
                petrov_rows=petrov_rows[:mode_count],
                modal_columns=modal_columns,
                side="bottom",
                negative_map=negative_map,
                forward=forward,
                backward=backward,
            )
            top_petrov = _insert_petrov_rows(
                matrix,
                rhs,
                system=top_system,
                interface_map=top_map,
                block=coupling.top,
                ar=top_ar,
                layout_map=layout.map_top,
                retained_old_to_new=layout.top_old_to_new,
                petrov_rows=petrov_rows[mode_count:],
                modal_columns=modal_columns,
                side="top",
                negative_map=negative_map,
                forward=forward,
                backward=backward,
            )
        finally:
            if bottom_ar is not None:
                bottom_ar.destroy()
                bottom_ar = None
            if top_ar is not None:
                top_ar.destroy()
                top_ar = None
        inserted.update(
            {f"bottom_{key}": value for key, value in bottom_petrov.items()}
        )
        inserted.update({f"top_{key}": value for key, value in top_petrov.items()})
        matrix.assemble()
        rhs.assemble()
        expected = (
            sum(map(len, bottom_map.retained_rows_by_rank))
            + sum(map(len, top_map.retained_rows_by_rank))
            + internal_count
        )
        if matrix.getSize() != (expected, expected):
            raise RuntimeError(
                "Strong-trace monolithic matrix is not the expected square."
            )
        return HybridStrongTraceDirectSystem(
            A=matrix,
            b=rhs,
            layout=layout,
            bottom_interface=bottom_map,
            top_interface=top_map,
            matrix_stats=_petsc_matrix_stats(matrix, assemble=False),
            block_shapes={
                "A_bottom": bottom_system.A.getSize(),
                "A_top": top_system.A.getSize(),
                "R_bottom": bottom_map.right_prolongation.getSize(),
                "R_top": top_map.right_prolongation.getSize(),
                "W_bottom": bottom_map.petrov_left_columns.getSize(),
                "W_top": top_map.petrov_left_columns.getSize(),
                "D_bottom": coupling.bottom.projection.getSize(),
                "D_top": coupling.top.projection.getSize(),
                "monolithic": matrix.getSize(),
            },
            inserted_nnz_by_block=inserted,
        )
    except Exception:
        if bottom_ar is not None:
            bottom_ar.destroy()
        if top_ar is not None:
            top_ar.destroy()
        if matrix is not None:
            matrix.destroy()
        if rhs is not None:
            rhs.destroy()
        bottom_map.destroy()
        if top_map is not None:
            top_map.destroy()
        raise


def _modal_vector(matrix: PETSc.Mat, values: np.ndarray) -> PETSc.Vec:
    vector = matrix.createVecRight()
    try:
        vector.set(PETSc.ScalarType(0.0))
        first, last = vector.getOwnershipRange()
        if last > first:
            vector.setValues(
                np.arange(first, last, dtype=PETSc.IntType),
                np.asarray(values[first:last], dtype=PETSc.ScalarType),
            )
        vector.assemble()
        return vector
    except Exception:
        vector.destroy()
        raise


def _reconstruct_local_carrier(
    system: HybridLocalDtnSystem,
    interface: HybridStrongTraceInterfaceMap,
    layout: HybridStrongTraceLayout,
    monolithic: PETSc.Vec,
    modal: np.ndarray,
    *,
    side: str,
    coupling: HybridInternalModeCoupling,
) -> tuple[PETSc.Vec, np.ndarray]:
    carrier = system.b.duplicate()
    modal_vector = None
    trace_vector = None
    success = False
    try:
        carrier.set(PETSc.ScalarType(0.0))
        rank = layout.comm.rank
        retained = interface.retained_rows_by_rank[rank]
        source_rows = (
            layout.map_bottom(retained)
            if side == "bottom"
            else layout.map_top(retained)
        )
        if len(retained):
            carrier.setValues(
                retained,
                monolithic.getValues(source_rows),
                addv=PETSc.InsertMode.INSERT_VALUES,
            )
        carrier.assemble()
        count = coupling.mode_count_per_direction
        negative_map = np.asarray(
            coupling.negative_trace_to_positive, dtype=np.complex128
        )
        if side == "bottom":
            trace_coefficients = modal[:count] + negative_map @ (
                np.asarray(coupling.propagation.backward.factors) * modal[count:]
            )
        elif side == "top":
            trace_coefficients = (
                np.asarray(coupling.propagation.forward.factors) * modal[:count]
                + negative_map @ modal[count:]
            )
        else:
            raise ValueError(f"Unknown Hybrid side {side!r}.")
        modal_vector = _modal_vector(interface.right_prolongation, trace_coefficients)
        trace_vector = interface.right_prolongation.createVecLeft()
        interface.right_prolongation.mult(modal_vector, trace_vector)
        carrier.axpy(PETSc.ScalarType(1.0), trace_vector)
        success = True
        return carrier, np.asarray(trace_coefficients, dtype=np.complex128)
    finally:
        if trace_vector is not None:
            trace_vector.destroy()
        if modal_vector is not None:
            modal_vector.destroy()
        if not success:
            carrier.destroy()


def _modal_from_monolithic(
    layout: HybridStrongTraceLayout, vector: PETSc.Vec
) -> np.ndarray:
    local = None
    if layout.comm.rank == layout.modal_owner:
        indices = layout.map_modal(range(layout.modal_count))
        local = np.asarray(vector.getValues(indices), dtype=np.complex128)
    return np.asarray(
        layout.comm.bcast(local, root=layout.modal_owner),
        dtype=np.complex128,
    )


def _subset_norm(vector: PETSc.Vec, rows: np.ndarray) -> float:
    first, last = vector.getOwnershipRange()
    local_rows = np.asarray(
        [int(row) for row in rows if first <= int(row) < last],
        dtype=np.int64,
    )
    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    local = (
        float(np.sum(np.abs(values[local_rows - first]) ** 2))
        if len(local_rows)
        else 0.0
    )
    return float(np.sqrt(vector.getComm().tompi4py().allreduce(local, op=MPI.SUM)))


def _tangential_trace_identity(
    carrier: PETSc.Vec,
    interface: HybridStrongTraceInterfaceMap,
    trace_coefficients: np.ndarray,
) -> dict[str, float]:
    source = _modal_vector(interface.right_prolongation, trace_coefficients)
    expected = interface.right_prolongation.createVecLeft()
    difference = carrier.duplicate()
    try:
        interface.right_prolongation.mult(source, expected)
        carrier.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        absolute = _subset_norm(difference, interface.interface_rows)
        scale = max(
            _subset_norm(carrier, interface.interface_rows),
            _subset_norm(expected, interface.interface_rows),
            1.0e-30,
        )
        return {
            "absolute": absolute,
            "relative": float(absolute / scale),
            "scale": scale,
        }
    finally:
        difference.destroy()
        expected.destroy()
        source.destroy()


@dataclass
class HybridStrongTraceDirectSolution:
    x: PETSc.Vec | None
    ksp: PETSc.KSP | None
    bottom: PETSc.Vec
    top: PETSc.Vec
    modal_amplitudes: np.ndarray
    relative_residual: float
    setup_seconds: float
    solve_seconds: float
    converged_reason: int
    tangential_e_continuity: dict[str, dict[str, float]]
    research_only: bool = True
    hybrid_p_production_qualified: bool = False
    joint_cauchy_qualified: bool = False
    all_channels_qualified: bool = False
    _factorization_released: bool = field(default=False, init=False, repr=False)
    _destroyed: bool = field(default=False, init=False, repr=False)

    def release_factorization(self) -> dict[str, Any]:
        if self._factorization_released:
            return {
                "released": False,
                "already_released": True,
                "retained_trace_carriers": True,
            }
        if self.x is not None:
            self.x.destroy()
            self.x = None
        if self.ksp is not None:
            self.ksp.destroy()
            self.ksp = None
        self._factorization_released = True
        return {
            "released": True,
            "already_released": False,
            "retained_trace_carriers": True,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.bottom.destroy()
        self.top.destroy()
        self.release_factorization()
        self._destroyed = True


def solve_hybrid_strong_trace_direct(
    strong_system: HybridStrongTraceDirectSystem,
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
    *,
    research_opt_in: bool = False,
) -> HybridStrongTraceDirectSolution:
    """Solve the opt-in system and qualify only complete tangential E continuity."""

    _require_research_opt_in(research_opt_in)
    ksp = PETSc.KSP().create(strong_system.layout.comm)
    x = None
    bottom = None
    top = None
    try:
        ksp.setType(PETSc.KSP.Type.PREONLY)
        ksp.setErrorIfNotConverged(True)
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.LU)
        pc.setFactorSolverType("mumps")
        ksp.setOperators(strong_system.A)
        started = time.perf_counter()
        ksp.setUp()
        setup_seconds = float(
            strong_system.layout.comm.allreduce(
                time.perf_counter() - started, op=MPI.MAX
            )
        )
        x = strong_system.b.duplicate()
        started = time.perf_counter()
        ksp.solve(strong_system.b, x)
        solve_seconds = float(
            strong_system.layout.comm.allreduce(
                time.perf_counter() - started, op=MPI.MAX
            )
        )
        residual = strong_system.b.duplicate()
        try:
            strong_system.A.mult(x, residual)
            residual.axpy(PETSc.ScalarType(-1.0), strong_system.b)
            relative_residual = float(
                residual.norm() / max(strong_system.b.norm(), 1.0e-30)
            )
        finally:
            residual.destroy()

        modal = _modal_from_monolithic(strong_system.layout, x)
        bottom, bottom_trace = _reconstruct_local_carrier(
            bottom_system,
            strong_system.bottom_interface,
            strong_system.layout,
            x,
            modal,
            side="bottom",
            coupling=coupling,
        )
        top, top_trace = _reconstruct_local_carrier(
            top_system,
            strong_system.top_interface,
            strong_system.layout,
            x,
            modal,
            side="top",
            coupling=coupling,
        )
        tangential_e = {
            "bottom": _tangential_trace_identity(
                bottom,
                strong_system.bottom_interface,
                bottom_trace,
            ),
            "top": _tangential_trace_identity(
                top,
                strong_system.top_interface,
                top_trace,
            ),
        }
        if (
            max(
                tangential_e["bottom"]["relative"],
                tangential_e["top"]["relative"],
            )
            > 1.0e-10
        ):
            raise RuntimeError("Strong-trace complete tangential E continuity failed.")
        result = HybridStrongTraceDirectSolution(
            x=x,
            ksp=ksp,
            bottom=bottom,
            top=top,
            modal_amplitudes=modal,
            relative_residual=relative_residual,
            setup_seconds=setup_seconds,
            solve_seconds=solve_seconds,
            converged_reason=int(ksp.getConvergedReason()),
            tangential_e_continuity=tangential_e,
        )
        x = None
        ksp = None
        bottom = None
        top = None
        return result
    except Exception:
        if bottom is not None:
            bottom.destroy()
        if top is not None:
            top.destroy()
        if x is not None:
            x.destroy()
        if ksp is not None:
            ksp.destroy()
        raise


def exact_trace_dense_fixture(
    A: np.ndarray,
    b: np.ndarray,
    D: np.ndarray,
    R: np.ndarray,
    W: np.ndarray,
    C: np.ndarray,
    L: np.ndarray,
    interface_rows: np.ndarray,
    *,
    research_opt_in: bool = False,
) -> dict[str, Any]:
    """Small research oracle for the strong tangential-trace algebra."""

    _require_research_opt_in(research_opt_in)

    A = np.asarray(A, dtype=np.complex128)
    b = np.asarray(b, dtype=np.complex128)
    D = np.asarray(D, dtype=np.complex128)
    R = np.asarray(R, dtype=np.complex128)
    W = np.asarray(W, dtype=np.complex128)
    C = np.asarray(C, dtype=np.complex128)
    L = np.asarray(L, dtype=np.complex128)
    interface = np.asarray(interface_rows, dtype=np.int64)
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise ValueError("Fixture A must be square.")
    if D.shape[1] != A.shape[0] or R.shape[0] != A.shape[0]:
        raise ValueError("Fixture D/R must use full local row numbering.")
    if W.shape != R.shape:
        raise ValueError("Fixture normalized left/right columns must have equal shape.")
    identity = D @ R
    if np.linalg.norm(identity - np.eye(identity.shape[0]), ord=np.inf) > 1.0e-12:
        raise ValueError("Fixture D R is not identity.")
    retained = np.asarray(
        [row for row in range(A.shape[0]) if row not in set(interface)],
        dtype=np.int64,
    )
    trial_retained = np.zeros((A.shape[0], len(retained)), dtype=np.complex128)
    trial_retained[retained, np.arange(len(retained))] = 1.0
    trial_modal = R @ L
    test_retained = trial_retained.conj().T
    petrov = W.conj().T
    trial = np.hstack((trial_retained, trial_modal))
    test = np.vstack((test_retained, petrov))
    reduced = test @ (A @ trial + np.hstack((np.zeros_like(trial_retained), C)))
    reduced_rhs = test @ b
    solution = np.linalg.solve(reduced, reduced_rhs)
    full = trial @ solution
    residual = A @ full + C @ solution[len(retained) :] - b
    return {
        "qualification": strong_trace_research_contract(),
        "reduced_matrix": reduced,
        "reduced_rhs": reduced_rhs,
        "solution": solution,
        "full_solution": full,
        "dr_identity_error": float(
            np.linalg.norm(identity - np.eye(identity.shape[0]), ord=np.inf)
        ),
        "noninterface_residual": float(np.linalg.norm(residual[retained])),
        "petrov_residual": float(np.linalg.norm(W.conj().T @ residual)),
        "trace_identity_residual": float(
            np.linalg.norm(
                full[interface] - (R @ (L @ solution[len(retained) :]))[interface]
            )
        ),
        "complete_tangential_e_continuity_pass": bool(
            np.linalg.norm(
                full[interface] - (R @ (L @ solution[len(retained) :]))[interface]
            )
            <= 1.0e-12
        ),
        "trace_complement_unknown_count": 0,
        "dense_interface_square_formed": False,
    }


__all__ = [
    "HybridStrongTraceDirectSolution",
    "HybridStrongTraceDirectSystem",
    "HybridStrongTraceInterfaceMap",
    "build_hybrid_strong_trace_direct_system",
    "exact_trace_dense_fixture",
    "solve_hybrid_strong_trace_direct",
    "strong_trace_research_contract",
]
