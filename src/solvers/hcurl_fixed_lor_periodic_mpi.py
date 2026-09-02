"""Distributed fixed x-y Floquet LOR action for the L1b MPI contract."""

from __future__ import annotations

from itertools import pairwise
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hcurl_fixed_lor_periodic import (
    FixedP6LORXYFloquetReferenceAction,
)

__all__ = [
    "FixedP6LORXYFloquetDistributedAction",
    "create_fixed_p6_lor_xy_floquet_distributed_action",
]

_GLOBAL_CELLS = 216
_GLOBAL_ROWS = 720
_CELL_ROWS = 12
_MAX_LOCAL_ROWS = 1024


def _as_int_array(values: Any) -> np.ndarray:
    return np.asarray(values, dtype=PETSc.IntType)


def _as_complex_array(values: Any) -> np.ndarray:
    return np.asarray(values, dtype=PETSc.ScalarType)


def _owner_ranges(vector: PETSc.Vec, comm: MPI.Comm) -> tuple[tuple[int, int], ...]:
    local_range = tuple(map(int, vector.getOwnershipRange()))
    ranges = tuple(
        tuple(map(int, value)) for value in comm.allgather(local_range)
    )
    if not ranges or ranges[0][0] != 0 or ranges[-1][1] != _GLOBAL_ROWS:
        raise RuntimeError(f"non-contiguous PETSc ownership ranges: {ranges}")
    if any(left[1] != right[0] for left, right in pairwise(ranges)):
        raise RuntimeError(f"non-contiguous PETSc ownership ranges: {ranges}")
    if sum(end - start for start, end in ranges) != _GLOBAL_ROWS:
        raise RuntimeError(f"incomplete PETSc ownership ranges: {ranges}")
    return ranges


def _metadata_from_root(
    comm: MPI.Comm,
    root_reference: FixedP6LORXYFloquetReferenceAction | None,
) -> tuple[dict[str, np.ndarray], int, int]:
    rank = comm.rank
    local_root_count = int(root_reference is not None)
    root_count = int(comm.allreduce(local_root_count, op=MPI.SUM))
    if root_count != 1 or (rank == 0) != (root_reference is not None):
        raise ValueError("root_reference must be non-None on rank0 only")
    if rank == 0:
        if root_reference is None:
            raise ValueError("rank0 requires the L1b-a reference action")
        l1a = root_reference.l1a_action
        payload: dict[str, np.ndarray] | None = {
            "cell_rows": _as_int_array(l1a.cell_rows),
            "cell_signs": np.asarray(l1a.cell_signs, dtype=np.float64),
            "cell_local_tensor": _as_complex_array(l1a.cell_local_tensor),
            "edge_rows": _as_int_array(root_reference.full_edge_to_reduced_row),
            "edge_phases": _as_complex_array(root_reference.full_edge_phase),
        }
    else:
        payload = None
    payload = comm.bcast(payload, root=0)
    metadata_bytes = sum(int(value.nbytes) for value in payload.values())
    if tuple(payload["cell_rows"].shape) != (_GLOBAL_CELLS, _CELL_ROWS):
        raise RuntimeError("L1b cell row metadata has the wrong shape")
    if tuple(payload["cell_signs"].shape) != (_GLOBAL_CELLS, _CELL_ROWS):
        raise RuntimeError("L1b cell sign metadata has the wrong shape")
    if tuple(payload["cell_local_tensor"].shape) != (_CELL_ROWS, _CELL_ROWS):
        raise RuntimeError("L1b cell tensor metadata has the wrong shape")
    if payload["edge_rows"].shape != (882,) or payload["edge_phases"].shape != (882,):
        raise RuntimeError("L1b edge metadata has the wrong shape")
    if not all(np.all(np.isfinite(value)) for value in payload.values()):
        raise FloatingPointError("L1b compact metadata is not finite")
    return payload, metadata_bytes, root_count


class FixedP6LORXYFloquetDistributedAction:
    """Owned-cell distributed MatPython action for the fixed 720-row quotient."""

    def __init__(
        self,
        comm: MPI.Comm,
        matrix: PETSc.Mat,
        scatter: PETSc.Scatter,
        source: PETSc.Vec,
        target: PETSc.Vec,
        cell_positions: np.ndarray,
        cell_signs: np.ndarray,
        cell_phases: np.ndarray,
        cell_tensor: np.ndarray,
        audit: dict[str, Any],
    ) -> None:
        self.comm = comm
        self.mat = matrix
        self._scatter = scatter
        self._source = source
        self._target = target
        self._cell_positions = cell_positions
        self._cell_signs = cell_signs
        self._cell_phases = cell_phases
        self._cell_tensor = cell_tensor
        self.audit = audit
        self.apply_count = 0
        self.destroyed = False

    def _apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.destroyed:
            raise RuntimeError("distributed L1b action is destroyed")
        if int(source.getSize()) != _GLOBAL_ROWS:
            raise ValueError("source Vec does not have the distributed 720-row layout")
        if int(target.getSize()) != _GLOBAL_ROWS:
            raise ValueError("target Vec does not have the distributed 720-row layout")
        target.set(0.0)
        self._source.set(0.0)
        self._scatter.scatter(
            source,
            self._source,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        source_values = self._source.getArray(readonly=True)
        self._target.set(0.0)
        target_values = self._target.getArray()
        for positions, signs, phases in zip(
            self._cell_positions,
            self._cell_signs,
            self._cell_phases,
            strict=True,
        ):
            local_input = signs * phases * source_values[positions]
            local_output = self._cell_tensor @ local_input
            if not np.all(np.isfinite(local_output)):
                raise FloatingPointError("local distributed L1b action is not finite")
            target_values[positions] += np.conj(phases) * signs * local_output
        self._scatter.scatter(
            self._target,
            target,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        self.apply_count += 1
        self.audit["apply_count"] = self.apply_count

    def mult(
        self,
        _matrix: PETSc.Mat,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        self._apply(source, target)

    def multHermitian(
        self,
        _matrix: PETSc.Mat,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        self._apply(source, target)

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if self.destroyed:
            return
        self._scatter.destroy()
        self._source.destroy()
        self._target.destroy()
        self.destroyed = True
        self.audit["lifecycle"].update(
            {
                "scatter_destroyed": True,
                "source_destroyed": True,
                "target_destroyed": True,
                "context_destroyed": True,
            }
        )


def create_fixed_p6_lor_xy_floquet_distributed_action(
    comm: MPI.Comm,
    root_reference: FixedP6LORXYFloquetReferenceAction | None,
) -> FixedP6LORXYFloquetDistributedAction:
    """Create the owned-cell distributed fixed L1b-a action."""

    if comm.size not in (1, 2):
        raise ValueError("the L1b-b contract supports only communicator size 1 or 2")
    payload, metadata_bytes, root_count = _metadata_from_root(comm, root_reference)
    cell_splits = np.array_split(np.arange(_GLOBAL_CELLS, dtype=np.int64), comm.size)
    local_cells = np.asarray(cell_splits[comm.rank], dtype=np.int64)
    expected_cells = (216,) if comm.size == 1 else (108, 108)
    cell_counts = tuple(int(value.size) for value in cell_splits)
    if cell_counts != expected_cells:
        raise RuntimeError(f"unexpected contiguous cell partition: {cell_counts}")
    full_cell_rows = payload["cell_rows"]
    full_cell_signs = payload["cell_signs"]
    full_cell_tensors = payload["cell_local_tensor"]
    full_edge_rows = payload["edge_rows"]
    full_edge_phases = payload["edge_phases"]
    local_cell_rows = full_cell_rows[local_cells].copy()
    local_cell_signs = full_cell_signs[local_cells].copy()
    local_cell_tensor = full_cell_tensors.copy()
    local_cell_reduced_rows = full_edge_rows[local_cell_rows]
    local_cell_phases = full_edge_phases[local_cell_rows]
    if not all(
        np.unique(rows).size == _CELL_ROWS for rows in local_cell_reduced_rows
    ):
        raise RuntimeError("a local cell contains duplicate reduced rows")
    union_rows = np.unique(local_cell_reduced_rows.reshape(-1))
    union_rows = np.asarray(union_rows, dtype=PETSc.IntType)
    cell_positions = np.asarray(
        np.searchsorted(union_rows, local_cell_reduced_rows),
        dtype=PETSc.IntType,
    )
    if not np.array_equal(union_rows[cell_positions], local_cell_reduced_rows):
        raise RuntimeError("owned-cell union indexing is inconsistent")
    union_counts = tuple(
        int(value) for value in comm.allgather(int(union_rows.size))
    )
    expected_union = (720,) if comm.size == 1 else (396, 396)
    if union_counts != expected_union:
        raise RuntimeError(f"unexpected owned-cell union rows: {union_counts}")
    if union_rows.size > _MAX_LOCAL_ROWS:
        raise RuntimeError("owned-cell union exceeds the L1b local-row cap")
    del payload, full_cell_rows, full_cell_signs, full_cell_tensors
    del full_edge_rows, full_edge_phases

    template = PETSc.Vec().createMPI(_GLOBAL_ROWS, comm=comm)
    owner_ranges = _owner_ranges(template, comm)
    local_range = owner_ranges[comm.rank]
    owned_union_rows = int(
        np.count_nonzero(
            (union_rows >= local_range[0]) & (union_rows < local_range[1])
        )
    )
    ghost_union_rows = int(union_rows.size - owned_union_rows)
    source = PETSc.Vec().createSeq(int(union_rows.size), comm=PETSc.COMM_SELF)
    target = source.duplicate()
    global_is = PETSc.IS().createGeneral(union_rows, comm=PETSc.COMM_SELF)
    local_is = PETSc.IS().createStride(
        int(union_rows.size), first=0, step=1, comm=PETSc.COMM_SELF
    )
    scatter = PETSc.Scatter().create(template, global_is, source, local_is)
    local_is.destroy()
    global_is.destroy()
    template.destroy()
    local_rows = int(local_range[1] - local_range[0])
    audit: dict[str, Any] = {
        "schema_version": "task040.fixed-lor.l1b-mpi.v1",
        "status": "fixed_p6_xy_floquet_owner_local_action_qualified",
        "scope": "research_reference_owner_local_not_lor_solver",
        "pass": True,
        "global_cells": _GLOBAL_CELLS,
        "global_rows": _GLOBAL_ROWS,
        "communicator_size": int(comm.size),
        "local_cell_counts": cell_counts,
        "local_cell_range": (int(local_cells[0]), int(local_cells[-1] + 1)),
        "local_union_rows": union_counts,
        "max_local_union_rows": max(union_counts),
        "local_owned_rows": tuple(
            int(value)
            for value in comm.allgather(owned_union_rows)
        ),
        "local_ghost_rows": tuple(
            int(value)
            for value in comm.allgather(ghost_union_rows)
        ),
        "owner_ranges": owner_ranges,
        "metadata_broadcast_bytes": metadata_bytes,
        "root_reference_rank_count": root_count,
        "distributed_full_basis_replica_rank_count": 0,
        "retained_full_basis_per_rank": False,
        "distributed_object_retains_full_basis": False,
        "full_basis_replication": False,
        "numeric_vector_allgather": False,
        "metadata_broadcast_only": True,
        "aij_materialized": False,
        "factor_counts": {
            "aij": 0,
            "full": 0,
            "full_side": 0,
            "full_cross": 0,
            "global": 0,
            "coarse": 0,
        },
        "apply_count": 0,
        "lifecycle": {
            "template_destroyed": True,
            "scatter_destroyed": False,
            "source_destroyed": False,
            "target_destroyed": False,
            "context_destroyed": False,
        },
        "local_rows": local_rows,
        "max_local_rows": max(union_counts),
        "local_row_cap": _MAX_LOCAL_ROWS,
        "local_cell_tensor_shape": tuple(map(int, local_cell_tensor.shape)),
        "shared_local_cell_tensor": True,
    }
    matrix = PETSc.Mat().createPython(
        ((local_rows, _GLOBAL_ROWS), (local_rows, _GLOBAL_ROWS)),
        comm=comm,
    )
    action = FixedP6LORXYFloquetDistributedAction(
        comm,
        matrix,
        scatter,
        source,
        target,
        cell_positions,
        local_cell_signs,
        local_cell_phases,
        local_cell_tensor,
        audit,
    )
    matrix.setPythonContext(action)
    matrix.setUp()
    return action
