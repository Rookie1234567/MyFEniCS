"""B0-S1c manufactured homogeneous right-FGMRES gate."""

from __future__ import annotations

import dolfinx_mpc
import numpy as np
import ufl
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.floquet_background_hcurl_single_harmonic import (
    build_single_x_phase_layout,
    create_single_harmonic_operator,
)
from src.test.test_319_task040_parallel_background_hcurl_s1 import _fixture
from src.test.test_319_task040_parallel_background_hcurl_s1b import (
    _active_columns,
)


class _B0RightPc:
    def __init__(self, matrix):
        self.matrix = matrix
        self.apply_count = 0
        self.destroyed = False
    def apply(self, _pc, source, target):
        if self.destroyed:
            raise RuntimeError("B0 PC adapter has been destroyed")
        self.matrix.mult(source, target)
        self.apply_count += 1
    def destroy(self, _pc=None):
        self.destroyed = True


def _true_relative(operator, rhs, solution):
    image = operator.createVecLeft()
    residual = rhs.duplicate()
    operator.mult(solution, image)
    rhs.copy(residual)
    residual.axpy(PETSc.ScalarType(-1.0), image)
    value = float(residual.norm()) / max(float(rhs.norm()), 1.0e-30)
    image.destroy()
    residual.destroy()
    return value

def _independent_amplitude(solution, columns):
    # PETSc Vec.dot(self, other) is other^H self: q_i^H q_j is q_j.dot(q_i).
    gram = np.asarray(
        [[columns[j].dot(columns[i]) for j in range(3)] for i in range(3)],
        dtype=np.complex128,
    )
    projected = np.asarray(
        [solution.dot(column) for column in columns], dtype=np.complex128
    )
    return np.linalg.solve(gram, projected)

def test_b0_s1c_single_harmonic_right_fgmres_manufactured():
    comm = MPI.COMM_WORLD
    box, V, mpc, phase = _fixture(comm)
    layout = build_single_x_phase_layout(V, mpc, phase)
    columns, phase_error = _active_columns(V, mpc, layout)
    b0_matrix = b0_context = exact = ksp = pc_context = None
    vectors = []
    try:
        b0_matrix, b0_context = create_single_harmonic_operator(
            columns,
            (0.17, 0.0, 0.0),
            mu_inv=0.9 - 0.07j,
            epsilon=1.8 + 0.12j,
            k0=1.3,
            shift=-0.4j,
        )
        u, v = ufl.TrialFunction(V), ufl.TestFunction(V)
        dx = ufl.Measure("dx", domain=box)
        form = fem.form(
            (
                (0.9 - 0.07j) * ufl.inner(ufl.curl(u), ufl.curl(v))
                - (1.3**2) * (1.8 + 0.12j) * ufl.inner(u, v)
            )
            * dx,
            dtype=PETSc.ScalarType,
        )
        exact = dolfinx_mpc.assemble_matrix(form, mpc, bcs=[])
        exact.assemble()
        if (exact.getSize(), exact.getLocalSize()) != (
            b0_matrix.getSize(),
            b0_matrix.getLocalSize(),
        ):
            raise RuntimeError("exact A and B0 Mat ownership sizes differ")
        ownership = tuple(int(x) for x in exact.getOwnershipRange())
        if ownership != tuple(int(x) for x in columns[0].getOwnershipRange()):
            raise RuntimeError("exact A ownership differs from Q")
        amplitude = np.asarray(
            [1.0 + 0.2j, -0.35 + 0.1j, 0.4 - 0.25j], dtype=PETSc.ScalarType
        )
        known = exact.createVecRight()
        known.set(0.0)
        for value, column in zip(amplitude, columns, strict=True):
            known.axpy(PETSc.ScalarType(value), column)
        rhs = exact.createVecLeft()
        exact.mult(known, rhs)
        solution = exact.createVecRight()
        solution.set(0.0)
        vectors.extend((known, rhs, solution))
        pc_context = _B0RightPc(b0_matrix)
        ksp = PETSc.KSP().create(comm)
        ksp.setOperators(exact)
        ksp.setType("fgmres")
        ksp.setGMRESRestart(8)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setTolerances(rtol=1.0e-12, atol=0.0, max_it=8)
        ksp.getPC().setType(PETSc.PC.Type.PYTHON)
        ksp.getPC().setPythonContext(pc_context)
        ksp.setUp()
        history = []
        ksp.setMonitor(
            lambda _k, iteration, norm: history.append(
                (int(iteration), float(norm))
            )
        )
        initial_residual = _true_relative(exact, rhs, solution)
        ksp.solve(rhs, solution)
        final_residual = _true_relative(exact, rhs, solution)
        reason = int(ksp.getConvergedReason())
        iterations = int(ksp.getIterationNumber())
        assert reason > 0
        assert iterations <= 8
        assert final_residual <= 1.0e-9
        envelope = _independent_amplitude(solution, columns)
        amplitude_error = float(np.linalg.norm(envelope - amplitude)) / max(
            float(np.linalg.norm(amplitude)), 1.0e-30
        )
        assert amplitude_error <= 1.0e-9
        solved = fem.Function(V)
        solved.x.array[: layout.owned_size] = solution.getArray(readonly=True)
        solved.x.scatter_forward()
        if not np.all(solved.x.array[layout.slave_local] == 0.0):
            raise RuntimeError("solved vector is not in MPC active representation")
        mpc.backsubstitution(solved)
        solved.x.scatter_forward()
        direct = fem.Function(V)
        def combined(x):
            values = np.zeros((3, x.shape[1]), dtype=PETSc.ScalarType)
            values[:] = amplitude[:, None] * np.exp(1j * 0.17 * x[0])
            return values
        direct.interpolate(combined)
        direct.x.scatter_forward()
        difference = solved.x.array[: layout.owned_size] - direct.x.array[
            : layout.owned_size
        ]
        local_num = float(np.vdot(difference, difference).real)
        direct_owned = direct.x.array[: layout.owned_size]
        local_den = float(np.vdot(direct_owned, direct_owned).real)
        ordinary_error = np.sqrt(comm.allreduce(local_num, op=MPI.SUM)) / max(
            np.sqrt(comm.allreduce(local_den, op=MPI.SUM)), 1.0e-30
        )
        assert ordinary_error <= 1.0e-9
        if comm.rank == 0:
            print(
                "B0_S1C_MANUFACTURED_RIGHT_FGMRES_PASS "
                f"phase={phase_error:.3e} initial={initial_residual:.3e} "
                f"final={final_residual:.3e} amplitude={amplitude_error:.3e} "
                f"ordinary={ordinary_error:.3e} reason={reason} iterations={iterations} "
                f"history={history} pc_applies={pc_context.apply_count}"
            )
    finally:
        if ksp is not None:
            ksp.destroy()
        assert pc_context is None or pc_context.destroyed
        for vector in vectors:
            vector.destroy()
        if b0_matrix is not None:
            b0_matrix.destroy()
        assert b0_context is None or b0_context.destroyed
        for column in columns:
            assert float(column.norm()) > 0.0
            column.destroy()
        if exact is not None:
            exact.destroy()
