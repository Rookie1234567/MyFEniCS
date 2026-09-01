"""B0-S1b single-harmonic distributed MatPython action."""

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.floquet_background_hcurl import maxwell_symbol_inverse
from src.solvers.floquet_background_hcurl_single_harmonic import (
    build_single_x_phase_layout,
    create_single_harmonic_operator,
)
from src.test.test_319_task040_parallel_background_hcurl_s1 import _fixture


def _active_columns(V, mpc, layout):
    columns = []
    phase_errors = []
    comm = V.mesh.comm
    for component in range(3):
        field = fem.Function(V)

        def plane_wave(x, component=component):
            values = np.zeros((3, x.shape[1]), dtype=PETSc.ScalarType)
            values[component, :] = np.exp(1j * 0.17 * x[0])
            return values

        field.interpolate(plane_wave)
        field.x.scatter_forward()
        values = np.asarray(field.x.array, dtype=np.complex128)
        expected = layout.coefficients * values[layout.master_local]
        difference = values[layout.slave_local] - expected
        numerator = comm.allreduce(float(np.vdot(difference, difference).real), op=MPI.SUM)
        denominator = comm.allreduce(float(np.vdot(expected, expected).real), op=MPI.SUM)
        phase_error = np.sqrt(numerator) / max(np.sqrt(denominator), 1.0e-30)
        assert phase_error <= 1.0e-9
        phase_errors.append(phase_error)
        mpc.homogenize(field)
        field.x.scatter_forward()
        assert np.all(field.x.array[layout.slave_local] == 0.0)
        source = field.x.petsc_vec
        column = PETSc.Vec().createMPI(
            (layout.owned_size, int(source.getSize())), comm=source.getComm()
        )
        column.getArray()[:] = field.x.array[: layout.owned_size]
        columns.append(column)
    return tuple(columns), max(phase_errors, default=0.0)


def _reference_action(x, columns):
    gram = np.asarray(
        [[columns[j].dot(columns[i]) for j in range(3)] for i in range(3)],
        dtype=np.complex128,
    )
    projected = np.asarray([x.dot(column) for column in columns], dtype=np.complex128)
    coefficients = np.linalg.solve(gram, projected)
    transformed = maxwell_symbol_inverse(
        (0.17, 0.0, 0.0),
        mu_inv=0.9 - 0.07j,
        epsilon=1.8 + 0.12j,
        k0=1.3,
        shift=-0.4j,
    ) @ coefficients
    result = x.duplicate()
    result.set(0.0)
    for value, column in zip(transformed, columns, strict=True):
        result.axpy(PETSc.ScalarType(value), column)
    return result


def _relative(actual, expected):
    difference = actual.duplicate()
    actual.copy(difference)
    difference.axpy(PETSc.ScalarType(-1.0), expected)
    result = float(difference.norm()) / max(float(expected.norm()), 1.0e-30)
    difference.destroy()
    return result


def _linear_combination(left, right, alpha, beta):
    result = left.duplicate()
    left.copy(result)
    result.scale(PETSc.ScalarType(alpha))
    result.axpy(PETSc.ScalarType(beta), right)
    return result


def test_b0_s1b_single_harmonic_matpython_action():
    comm = MPI.COMM_WORLD
    _box, V, mpc, phase = _fixture(comm)
    layout = build_single_x_phase_layout(V, mpc, phase)
    columns, phase_error = _active_columns(V, mpc, layout)
    matrix = context = None
    vectors = []
    try:
        assert len(columns) == 3
        matrix, context = create_single_harmonic_operator(
            columns,
            (0.17, 0.0, 0.0),
            mu_inv=0.9 - 0.07j,
            epsilon=1.8 + 0.12j,
            k0=1.3,
            shift=-0.4j,
        )
        x = matrix.createVecRight()
        first, last = (int(value) for value in x.getOwnershipRange())
        indices = np.arange(first, last, dtype=float)
        x.getArray()[:] = np.sin(0.17 * (indices + 1.0)) + 1j * np.cos(
            0.11 * (indices + 2.0)
        )
        y = matrix.createVecLeft()
        vectors.extend((x, y))
        for column in columns:
            assert column.getSize() == x.getSize()
            assert column.getOwnershipRange() == x.getOwnershipRange()
        assert y.getOwnershipRange() == x.getOwnershipRange()
        matrix.mult(x, y)
        reference = _reference_action(x, columns)
        vectors.append(reference)
        action_error = _relative(y, reference)
        assert action_error <= 1.0e-10
        repeat = matrix.createVecLeft()
        vectors.append(repeat)
        matrix.mult(x, repeat)
        repeat_error = _relative(repeat, y)
        assert repeat_error <= 1.0e-10

        x1 = x.duplicate()
        x2 = x.duplicate()
        x1.set(0.0)
        x2.set(0.0)
        x1.getArray()[:] = np.sin(0.07 * (indices + 1.0)) + 0.2j
        x2.getArray()[:] = np.cos(0.13 * (indices + 2.0)) - 0.3j
        combo = _linear_combination(x1, x2, 0.7 - 0.1j, -0.2 + 0.4j)
        y1 = matrix.createVecLeft()
        y2 = matrix.createVecLeft()
        yc = matrix.createVecLeft()
        vectors.extend((x1, x2, combo, y1, y2, yc))
        matrix.mult(x1, y1)
        matrix.mult(x2, y2)
        matrix.mult(combo, yc)
        expected_combo = _linear_combination(y1, y2, 0.7 - 0.1j, -0.2 + 0.4j)
        vectors.append(expected_combo)
        linearity_error = _relative(yc, expected_combo)
        assert linearity_error <= 1.0e-10
        assert context.apply_count == 5
        assert layout.global_cross_owner_count >= (1 if comm.size == 2 else 0)
        if comm.rank == 0:
            print(
                "B0_S1B_SINGLE_HARMONIC_ACTION_PASS "
                f"phase_error={phase_error:.3e} action_error={action_error:.3e} "
                f"repeat_error={repeat_error:.3e} linearity_error={linearity_error:.3e} "
                f"gram_rank={np.linalg.matrix_rank(context.gram)} "
                f"gram_cond={np.linalg.cond(context.gram):.3e} "
                f"cross_owner={layout.global_cross_owner_count} applies={context.apply_count}"
            )
    finally:
        if matrix is not None:
            matrix.destroy()
        assert context is None or context.destroyed
        if columns:
            assert float(columns[0].norm()) > 0.0
        for vector in vectors:
            vector.destroy()
        for column in columns:
            column.destroy()
