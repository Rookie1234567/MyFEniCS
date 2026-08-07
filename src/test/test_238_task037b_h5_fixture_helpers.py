from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from petsc4py import PETSc

from benchmarks.run_task032_phase6_augmented import (
    H5_FROZEN_RANDOM_SEEDS,
    _h5_frozen_mode_selection,
    _h5_indexed_random_values,
    _h5_rhs_set,
)


def _basis(direction: str) -> SimpleNamespace:
    modes = [
        SimpleNamespace(
            kind=(
                "propagating"
                if index == 1
                else "evanescent"
                if index == 3
                else "propagating"
                if index == 119
                else "cutoff_or_near_zero_flux"
            ),
            beta=complex(index + 1, 0.1 if direction == "positive" else -0.1),
        )
        for index in range(120)
    ]
    return SimpleNamespace(modes=modes)


def _traction_matrix(rows: int, columns: int, offset: float) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        size=(rows, columns), nnz=columns, comm=PETSc.COMM_WORLD
    )
    matrix.setUp()
    for column in range(columns):
        matrix.setValue(column % rows, column, offset + column + 1.0j)
    matrix.assemble()
    return matrix


def _relative_vec_error(
    actual: PETSc.Vec, expected: PETSc.Vec, scale=1.0 + 0.0j
) -> float:
    difference = actual.duplicate()
    try:
        actual.copy(difference)
        difference.axpy(PETSc.ScalarType(-scale), expected)
        return float(
            difference.norm()
            / max(float(actual.norm()), abs(scale) * float(expected.norm()), 1.0e-30)
        )
    finally:
        difference.destroy()


def test_h5_frozen_selection_random_partition_and_eleven_rhs() -> None:
    propagation = SimpleNamespace(
        forward=SimpleNamespace(
            factors=tuple(2.0 + 0.1j * index for index in range(120))
        ),
        backward=SimpleNamespace(
            factors=tuple(3.0 + 0.2j * index for index in range(120))
        ),
    )
    selections = _h5_frozen_mode_selection(_basis("positive"), _basis("negative"))
    assert len(selections) == 6
    assert [item["local_mode_index"] for item in selections] == [
        1,
        3,
        119,
        1,
        3,
        119,
    ]
    assert [item["global_modal_column"] for item in selections] == [
        1,
        3,
        119,
        121,
        123,
        239,
    ]
    assert len({item["global_modal_column"] for item in selections}) == 6
    assert all(item["criterion"] for item in selections)

    ids = np.arange(12, dtype=np.uint64)
    first = _h5_indexed_random_values(ids[:5], 3701)
    second = _h5_indexed_random_values(ids[5:], 3701)
    whole = _h5_indexed_random_values(ids, 3701)
    np.testing.assert_array_equal(np.concatenate((first, second)), whole)
    assert whole.dtype == np.complex128

    b = PETSc.Vec().createMPI(5, comm=PETSc.COMM_WORLD)
    b.set(1.0 + 0.0j)
    b.assemble()
    operator = PETSc.Mat().createAIJ(size=(5, 5), nnz=1, comm=PETSc.COMM_WORLD)
    operator.setUp()
    for row in range(5):
        operator.setValue(row, row, 1.0)
    operator.assemble()
    block = SimpleNamespace(
        positive_traction=_traction_matrix(5, 120, 1.0),
        negative_traction=_traction_matrix(5, 120, 2.0),
    )
    action = SimpleNamespace(A=operator, b=b)
    bottom = []
    top = []
    try:
        bottom = _h5_rhs_set(
            action,
            block,
            selections,
            side="bottom",
            propagation=propagation,
        )
        top = _h5_rhs_set(
            action,
            block,
            selections,
            side="top",
            propagation=propagation,
        )
        assert len(bottom) == len(top) == 11
        assert [name for name, _vector, _metadata in bottom[:5]] == [
            "physical",
            "random_seed_3701",
            "random_seed_3702",
            "random_seed_3703",
            "random_seed_3704",
        ]
        assert [metadata["seed"] for _name, _vector, metadata in bottom[1:5]] == list(
            H5_FROZEN_RANDOM_SEEDS
        )
        for _name, vector, _metadata in [*bottom[1:5], *top[1:5]]:
            assert abs(float(vector.norm()) - 1.0) <= 1.0e-13
        assert bottom[5][2]["propagation_factor"] == [1.0, 0.0]
        assert top[5][2]["propagation_factor"] == [2.0, 0.1]
        assert bottom[8][2]["propagation_factor"] == [3.0, 0.2]
        assert top[8][2]["propagation_factor"] == [1.0, 0.0]
        assert _relative_vec_error(top[5][1], bottom[5][1], scale=2.0 + 0.1j) <= 1.0e-14
        assert _relative_vec_error(bottom[8][1], top[8][1], scale=3.0 + 0.2j) <= 1.0e-14
    finally:
        for _name, vector, _metadata in [*bottom, *top]:
            vector.destroy()
        block.negative_traction.destroy()
        block.positive_traction.destroy()
        operator.destroy()
        b.destroy()
