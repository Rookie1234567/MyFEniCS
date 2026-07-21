"""Distributed PETSc matrix diagnostics without Python object collectives."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc


@dataclass(frozen=True)
class ActiveColumnCount:
    """Result and bounded-memory telemetry for a distributed column count."""

    global_count: int
    global_column_count: int
    local_unique_candidates: int
    marker_owned_entries: int
    marker_payload_bytes_local: int
    submitted_payload_bytes_local: int
    communication: str = "PETSc Vec ADD_VALUES owner routing + scalar MPI allreduce"
    memory_complexity: str = "O(global_columns / mpi_size + local_active_columns)"
    python_object_allgather_used: bool = False

    def to_dict(self) -> dict[str, int | str | bool]:
        return asdict(self)


def distributed_active_column_count(matrix: PETSc.Mat) -> ActiveColumnCount:
    """Count nonempty matrix columns using a distributed PETSc marker vector.

    Each rank submits its locally observed unique column IDs to the PETSc owner
    of that marker entry.  Only one scalar count is reduced globally; no rank
    receives the global column-ID set.
    """

    first, last = matrix.getOwnershipRange()
    local_columns: set[int] = set()
    for row in range(first, last):
        columns, values = matrix.getRow(row)
        local_columns.update(
            int(column)
            for column, value in zip(columns, values, strict=True)
            if value != 0
        )

    global_columns = int(matrix.getSize()[1])
    marker = PETSc.Vec().createMPI(global_columns, comm=matrix.getComm())
    try:
        marker.set(PETSc.ScalarType(0.0))
        if local_columns:
            indices = np.fromiter(
                sorted(local_columns), dtype=PETSc.IntType, count=len(local_columns)
            )
            values = np.ones(len(indices), dtype=PETSc.ScalarType)
            marker.setValues(indices, values, addv=PETSc.InsertMode.ADD_VALUES)
        marker.assemblyBegin()
        marker.assemblyEnd()
        owned = marker.getArray(readonly=True)
        local_count = int(np.count_nonzero(owned))
        marker_owned_entries = int(owned.size)
        del owned
        global_count = int(
            matrix.getComm().tompi4py().allreduce(local_count, op=MPI.SUM)
        )
    finally:
        marker.destroy()

    return ActiveColumnCount(
        global_count=global_count,
        global_column_count=global_columns,
        local_unique_candidates=len(local_columns),
        marker_owned_entries=marker_owned_entries,
        marker_payload_bytes_local=(
            marker_owned_entries * np.dtype(PETSc.ScalarType).itemsize
        ),
        submitted_payload_bytes_local=(
            len(local_columns)
            * (
                np.dtype(PETSc.IntType).itemsize
                + np.dtype(PETSc.ScalarType).itemsize
            )
        ),
    )
