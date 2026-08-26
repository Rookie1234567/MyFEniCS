"""Focused contracts for the matrix-free p6 shell and fixed nested cycle."""

from __future__ import annotations

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.fullspace_same_mesh_hcurl_pmg_p6 import (
    P6_NESTED_LEVELS,
    P6_NESTED_PAIRS,
    SameMeshP6MatrixFreeShell,
    SameMeshP6NestedVcycle,
)


def _diagonal_matrix(values: tuple[complex, ...]) -> PETSc.Mat:
    size = len(values)
    matrix = PETSc.Mat().createAIJ(
        ((size, size), (size, size)), comm=MPI.COMM_SELF
    )
    matrix.setUp()
    for index, value in enumerate(values):
        matrix.setValue(index, index, value)
    matrix.assemble()
    return matrix


class _BorrowedAction:
    def __init__(self, matrix: PETSc.Mat) -> None:
        self.matrix = matrix
        self.audit = {"slave_row_identity": True}
        self.output = matrix.createVecLeft()
        self.apply_count = 0
        self.destroyed = False
        self.output_destroyed = False

    def apply(self, source: PETSc.Vec) -> PETSc.Vec:
        if self.destroyed:
            raise RuntimeError("borrowed action was destroyed")
        self.matrix.mult(source, self.output)
        self.apply_count += 1
        return self.output

    def destroy(self) -> None:
        if self.destroyed:
            return
        self.output.destroy()
        self.output_destroyed = True
        self.destroyed = True


class _CountingSmoother:
    def __init__(self) -> None:
        self.apply_count = 0
        self.destroyed = False

    def apply_into(self, source: PETSc.Vec, target: PETSc.Vec) -> dict[str, object]:
        source.copy(target)
        target.scale(0.25)
        self.apply_count += 1
        return {"apply_count": self.apply_count}

    def destroy(self) -> None:
        self.destroyed = True


class _CountingP63:
    def __init__(self) -> None:
        self.events: list[str] = []

    def apply_adjoint_into(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.events.append("p63_adjoint")
        target.array[:] = source.array[: target.array.size]

    def apply_primal_into(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.events.append("p63_primal")
        target.array[:] = 0.0 + 0.0j
        target.array[: source.array.size] = source.array
        target.array[-1] = 11.0 + 7.0j


class _CountingLowerCycle:
    def __init__(self) -> None:
        self.apply_count = 0

    def apply_into(self, source: PETSc.Vec, target: PETSc.Vec) -> dict[str, object]:
        source.copy(target)
        target.scale(0.5)
        self.apply_count += 1
        return {
            "p1_solve_count": 1,
            "p1_solve_total": self.apply_count,
        }


def test_p6_shell_copies_borrowed_action_and_exact_diagonal() -> None:
    action_matrix = _diagonal_matrix((2.0 + 0.0j, 3.0 + 0.0j, 5.0 + 0.0j))
    diagonal = action_matrix.createVecRight()
    action_matrix.getDiagonal(diagonal)
    action = _BorrowedAction(action_matrix)
    shell = SameMeshP6MatrixFreeShell(action, diagonal)
    source = shell.matrix.createVecRight()
    target = shell.matrix.createVecLeft()
    observed_diagonal = shell.matrix.createVecRight()
    try:
        source.array[:] = (1.0 + 2.0j, -2.0 + 0.5j, 3.0 - 1.0j)
        shell.matrix.mult(source, target)
        np.testing.assert_allclose(
            target.array,
            source.array * np.asarray((2.0, 3.0, 5.0)),
        )
        assert action.apply_count == 1
        assert not action.output_destroyed
        shell.matrix.getDiagonal(observed_diagonal)
        np.testing.assert_allclose(observed_diagonal.array, (2.0, 3.0, 5.0))
        assert shell.audit["p6_global_aij"] is False
    finally:
        source.destroy()
        target.destroy()
        observed_diagonal.destroy()
        shell.destroy()
        shell.destroy()
        action_matrix.destroy()
    assert action.destroyed
    assert action.output_destroyed


def test_fixed_nested_p6_cycle_orders_reuses_and_zeroes_owned_slave() -> None:
    p6_matrix = _diagonal_matrix((2.0 + 0.0j, 3.0 + 0.0j, 4.0 + 0.0j, 6.0 + 0.0j))
    diagonal = p6_matrix.createVecRight()
    p6_matrix.getDiagonal(diagonal)
    action = _BorrowedAction(p6_matrix)
    shell = SameMeshP6MatrixFreeShell(action, diagonal)
    p3_matrix = _diagonal_matrix((2.0 + 0.0j, 4.0 + 0.0j, 8.0 + 0.0j))
    smoother = _CountingSmoother()
    transfer = _CountingP63()
    lower = _CountingLowerCycle()
    cycle = SameMeshP6NestedVcycle(
        shell,
        lower,
        transfer,
        p3_matrix,
        smoother=smoother,
        owned_slave_indices=np.asarray((3,), dtype=np.int32),
    )
    vectors: list[PETSc.Vec] = []
    try:
        assert cycle.audit["levels"] == list(P6_NESTED_LEVELS)
        assert cycle.audit["pairs"] == [list(pair) for pair in P6_NESTED_PAIRS]
        rhs_a = p6_matrix.createVecLeft()
        rhs_b = p6_matrix.createVecLeft()
        rhs_combo = p6_matrix.createVecLeft()
        out_a = p6_matrix.createVecRight()
        out_repeat = p6_matrix.createVecRight()
        out_b = p6_matrix.createVecRight()
        out_combo = p6_matrix.createVecRight()
        expected = p6_matrix.createVecRight()
        vectors.extend(
            (rhs_a, rhs_b, rhs_combo, out_a, out_repeat, out_b, out_combo, expected)
        )
        rhs_a.array[:] = (1.0 + 1.0j, 2.0 - 1.0j, -1.0 + 0.5j, 0.0j)
        rhs_b.array[:] = (-2.0 + 0.25j, 0.5 + 1.0j, 3.0 - 2.0j, 0.0j)
        rhs_combo.array[:] = rhs_a.array + rhs_b.array
        input_a = rhs_a.array.copy()
        input_b = rhs_b.array.copy()
        input_combo = rhs_combo.array.copy()
        work_ids = tuple(id(vector) for vector in cycle.work_vectors)

        cycle.apply_into(rhs_a, out_a)
        out_a.copy(expected)
        cycle.apply_into(rhs_a, out_repeat)
        cycle.apply_into(rhs_b, out_b)
        cycle.apply_into(rhs_combo, out_combo)
        expected.axpy(1.0, out_b)

        np.testing.assert_allclose(out_repeat.array, out_a.array)
        np.testing.assert_allclose(out_combo.array, expected.array)
        assert np.all(np.isfinite(out_combo.array))
        assert out_combo.array[3] == 0.0j
        assert np.array_equal(rhs_a.array, input_a)
        assert np.array_equal(rhs_b.array, input_b)
        assert np.array_equal(rhs_combo.array, input_combo)
        assert tuple(id(vector) for vector in cycle.work_vectors) == work_ids
        assert transfer.events == [
            "p63_adjoint", "p63_primal",
            "p63_adjoint", "p63_primal",
            "p63_adjoint", "p63_primal",
            "p63_adjoint", "p63_primal",
        ]
        assert smoother.apply_count == 8
        assert lower.apply_count == 4
        assert action.apply_count == 8
        facts = cycle.last_apply_facts
        assert facts["p6_smoother_apply_count"] == 2
        assert facts["p63_adjoint_count"] == 1
        assert facts["p63_primal_count"] == 1
        assert facts["p1_solve_count"] == 1
        assert facts["p6_smoother_apply_total"] == 8
        assert facts["p63_adjoint_total"] == 4
        assert facts["p63_primal_total"] == 4
        assert facts["lower_cycle_total"] == 4
        assert facts["apply_count"] == 4
    finally:
        for vector in vectors:
            vector.destroy()
        cycle.destroy()
        cycle.destroy()
        p3_matrix.destroy()
        p6_matrix.destroy()
    assert action.destroyed
