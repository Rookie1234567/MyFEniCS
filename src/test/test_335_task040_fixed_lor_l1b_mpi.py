"""Task040 L1b-b distributed fixed x-y Floquet LOR contract tests."""

from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI

from src.solvers.hcurl_fixed_lor_periodic import (
    build_fixed_p6_lor_xy_floquet_reference_action,
)
from src.solvers.hcurl_fixed_lor_periodic_mpi import (
    FixedP6LORXYFloquetDistributedAction,
    create_fixed_p6_lor_xy_floquet_distributed_action,
)

_GLOBAL_ROWS = 720
_TINY = 1.0e-30


def _distributed_relative(actual: np.ndarray, expected: np.ndarray, comm: MPI.Comm) -> float:
    difference = np.asarray(actual, dtype=np.complex128) - np.asarray(
        expected, dtype=np.complex128
    )
    numerator = comm.allreduce(float(np.vdot(difference, difference).real), op=MPI.SUM)
    denominator = comm.allreduce(
        float(np.vdot(expected, expected).real), op=MPI.SUM
    )
    return float(np.sqrt(numerator / max(denominator, _TINY)))


def _distributed_inner(first: np.ndarray, second: np.ndarray, comm: MPI.Comm) -> complex:
    return complex(comm.allreduce(complex(np.vdot(first, second)), op=MPI.SUM))


def _fill(vector, shift: float) -> None:
    start, stop = map(int, vector.getOwnershipRange())
    indices = np.arange(start, stop, dtype=np.float64)
    values = (0.21 + shift + 0.0013 * indices) + 1j * (
        -0.17 + 0.0007 * indices
    )
    vector.getArray()[:] = values


def _scatter_oracle(comm: MPI.Comm, reference, values: np.ndarray, ranges):
    slices = None
    if comm.rank == 0:
        result = reference.apply_lor_streamed(values)
        slices = [result[start:stop].copy() for start, stop in ranges]
    return comm.scatter(slices, root=0)


def _root_values(comm: MPI.Comm, shift: float) -> np.ndarray | None:
    if comm.rank != 0:
        return None
    return np.asarray(
        [_fill_value(index, shift) for index in range(_GLOBAL_ROWS)],
        dtype=np.complex128,
    )


@pytest.fixture(scope="module")
def distributed_action():
    comm = MPI.COMM_WORLD
    reference = (
        build_fixed_p6_lor_xy_floquet_reference_action()
        if comm.rank == 0
        else None
    )
    action: FixedP6LORXYFloquetDistributedAction | None = None
    try:
        action = create_fixed_p6_lor_xy_floquet_distributed_action(
            comm, reference
        )
        yield comm, action, reference
    finally:
        if action is not None:
            action.destroy()
            assert action.destroyed
            assert action.audit["lifecycle"]["context_destroyed"] is True
            action.mat.destroy()
        reference = None


def test_task040_l1b_mpi_contract_ownership_and_lifecycle(distributed_action) -> None:
    comm, action, _reference = distributed_action
    audit = action.audit
    expected_cells = (216,) if comm.size == 1 else (108, 108)
    expected_union = (720,) if comm.size == 1 else (396, 396)
    expected_owned = (720,) if comm.size == 1 else (252, 252)
    expected_ghost = (0,) if comm.size == 1 else (144, 144)
    expected_ranges = ((0, 720),) if comm.size == 1 else ((0, 360), (360, 720))
    assert comm.size in (1, 2)
    assert audit["schema_version"] == "task040.fixed-lor.l1b-mpi.v1"
    assert audit["status"] == "fixed_p6_xy_floquet_owner_local_action_qualified"
    assert audit["scope"] == "research_reference_owner_local_not_lor_solver"
    assert audit["pass"] is True
    assert action.mat.getSize() == (_GLOBAL_ROWS, _GLOBAL_ROWS)
    assert audit["global_cells"] == 216
    assert audit["global_rows"] == _GLOBAL_ROWS
    assert audit["local_cell_counts"] == expected_cells
    assert audit["local_union_rows"] == expected_union
    assert audit["local_owned_rows"] == expected_owned
    assert audit["local_ghost_rows"] == expected_ghost
    assert audit["max_local_rows"] == max(expected_union)
    assert audit["max_local_rows"] <= 720 <= audit["local_row_cap"]
    assert audit["local_cell_tensor_shape"] == (12, 12)
    assert audit["shared_local_cell_tensor"] is True
    assert tuple(audit["owner_ranges"]) == expected_ranges
    assert audit["root_reference_rank_count"] == 1
    assert audit["distributed_full_basis_replica_rank_count"] == 0
    assert audit["retained_full_basis_per_rank"] is False
    assert audit["distributed_object_retains_full_basis"] is False
    assert not hasattr(action, "root_reference")
    assert audit["metadata_broadcast_only"] is True
    assert audit["numeric_vector_allgather"] is False
    assert audit["aij_materialized"] is False
    assert all(value == 0 for value in audit["factor_counts"].values())
    assert action.apply_count == 0
    assert action.destroyed is False
    assert audit["lifecycle"]["context_destroyed"] is False


def test_task040_l1b_mpi_complex_action_and_hermitian(distributed_action) -> None:
    comm, action, reference = distributed_action
    ranges = tuple(tuple(map(int, item)) for item in action.audit["owner_ranges"])
    x = action.mat.createVecRight()
    x2 = action.mat.createVecRight()
    y = action.mat.createVecLeft()
    y_repeat = action.mat.createVecLeft()
    y2 = action.mat.createVecLeft()
    mixed = action.mat.createVecRight()
    mixed_y = action.mat.createVecLeft()
    hermitian_y = action.mat.createVecLeft()
    alpha, beta = 0.63 - 0.21j, -0.37 + 0.18j
    try:
        _fill(x, 0.0)
        _fill(x2, 0.41)
        x.copy(mixed)
        mixed.scale(alpha)
        mixed.axpy(beta, x2)
        expected_x = _scatter_oracle(
            comm, reference, _root_values(comm, 0.0), ranges
        )
        expected_x2 = _scatter_oracle(
            comm, reference, _root_values(comm, 0.41), ranges
        )
        action.mat.mult(x, y)
        action.mat.mult(x, y_repeat)
        action.mat.mult(x2, y2)
        action.mat.mult(mixed, mixed_y)
        action.mat.multHermitian(x, hermitian_y)
        y_local = np.asarray(y.getArray(readonly=True)).copy()
        y_repeat_local = np.asarray(y_repeat.getArray(readonly=True)).copy()
        y2_local = np.asarray(y2.getArray(readonly=True)).copy()
        mixed_local = np.asarray(mixed_y.getArray(readonly=True)).copy()
        hermitian_local = np.asarray(hermitian_y.getArray(readonly=True)).copy()
        expected_x = np.asarray(expected_x, dtype=np.complex128)
        expected_x2 = np.asarray(expected_x2, dtype=np.complex128)
        oracle_error = _distributed_relative(y_local, expected_x, comm)
        repeat_error = _distributed_relative(y_repeat_local, y_local, comm)
        linearity_error = _distributed_relative(
            mixed_local, alpha * expected_x + beta * expected_x2, comm
        )
        hermitian_error = _distributed_relative(hermitian_local, expected_x, comm)
        adjoint_left = _distributed_inner(y_local, np.asarray(x2.getArray()), comm)
        adjoint_right = _distributed_inner(
            np.asarray(x.getArray()), y2_local, comm
        )
        adjoint_denominator = max(
            float(y.norm()) * float(x2.norm()),
            float(x.norm()) * float(y2.norm()),
            _TINY,
        )
        adjoint_error = abs(adjoint_left - adjoint_right) / adjoint_denominator
        assert oracle_error <= 1.0e-10
        assert repeat_error <= 1.0e-10
        assert linearity_error <= 1.0e-10
        assert hermitian_error <= 2.0e-11
        assert adjoint_error <= 2.0e-11
        assert action.apply_count == 5
        assert action.audit["apply_count"] == 5
        if comm.rank == 0:
            print(
                "TASK040_L1B_MPI "
                f"size={comm.size} cells={action.audit['local_cell_counts']} "
                f"union={action.audit['local_union_rows']} "
                f"ranges={action.audit['owner_ranges']} "
                f"oracle={oracle_error:.17g} repeat={repeat_error:.17g} "
                f"linearity={linearity_error:.17g} adjoint={adjoint_error:.17g} "
                f"multHermitian={hermitian_error:.17g} "
                f"apply_count={action.apply_count} "
                f"metadata_bytes={action.audit['metadata_broadcast_bytes']}"
            )
    finally:
        for vector in (x, x2, y, y_repeat, y2, mixed, mixed_y, hermitian_y):
            vector.destroy()


def _fill_value(index: int, shift: float) -> complex:
    return (0.21 + shift + 0.0013 * index) + 1j * (-0.17 + 0.0007 * index)
