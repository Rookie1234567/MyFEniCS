"""Small algebraic adapter checks, native PETSc ABI only, no mesh/forms/JIT."""

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.learned_coarse_inverse import reference_solve
from src.solvers.p6_cell_condensed_action import P6CellCondensedAction
from src.test.test_task039extra_v20_noncommuting_contract import _problem


def test_offline_reference_uses_qualified_repeated_api_across_rhs():
    from src.solvers.coarse_inverse_protocol import CoarseRHS

    _, _, action = _problem()
    dense = np.column_stack(
        [action.apply(np.eye(4, dtype=np.complex128)[:, i]) for i in range(4)]
    )
    matrix = PETSc.Mat().createDense([4, 4], comm=MPI.COMM_SELF)
    matrix.setUp()
    matrix.setValues(range(4), range(4), dense)
    matrix.assemble()

    class RepeatedFactor:
        calls = 0

        def solve(self, *_):
            raise AssertionError("MUMPS one-shot solve is forbidden for multiple RHS")

        def solve_repeated(self, b, x):
            self.calls += 1
            x.array[:] = np.linalg.solve(dense, b.array)

    factor = RepeatedFactor()
    try:
        for phase in (1.0, 1j):
            rhs = CoarseRHS(
                np.full(4, phase, dtype=np.complex128),
                np.full(2, -phase, dtype=np.complex128),
            )
            x, refinement = reference_solve(matrix, action, rhs, factor)
            b = action.reduce_rhs(rhs.fe, port_rhs=rhs.port, rhs_is_mpc_dual=True)
            assert np.linalg.norm(dense @ x - b) / np.linalg.norm(b) < 1e-13
            assert refinement == 0
        assert factor.calls == 2
    finally:
        matrix.destroy()
        action.destroy()


def test_borrowed_matrix_default_rejection_and_p4_ownership():
    condensed, _, old = _problem()
    materialized = PETSc.Mat().createDense([4, 4], comm=MPI.COMM_SELF)
    materialized.setUp()
    dense = np.column_stack(
        [old.apply(np.eye(4, dtype=np.complex128)[:, i]) for i in range(4)]
    )
    materialized.setValues(range(4), range(4), dense)
    materialized.assemble()
    condensed.matrix = materialized
    condensed.build_audit["local_tensor_dimension"] = 300
    original_hp = old.H_p - old._cells[0].Hlocal
    p4 = None
    try:
        with pytest.raises(ValueError, match="cannot borrow"):
            P6CellCondensedAction(condensed, H_p=old.H_p)
        with pytest.raises(ValueError, match="caller-owned"):
            P6CellCondensedAction(
                condensed, H_p=old.H_p, borrowed_p4_witness=True, owns_condensed=True
            )
        p4 = P6CellCondensedAction(
            condensed,
            H_p=original_hp,
            port_terms=old._port_terms,
            borrowed_p4_witness=True,
        )
        x = np.array([1 + 2j, 3 - 1j, -0.5 + 0.2j, 0.7j], dtype=np.complex128)
        np.testing.assert_allclose(p4.apply(x), dense @ x, rtol=2e-13, atol=2e-13)
        np.testing.assert_array_equal(
            p4.reduce_rhs(
                np.ones(4, dtype=np.complex128),
                port_rhs=np.ones(2, dtype=np.complex128),
            ),
            old.reduce_rhs(
                np.ones(4, dtype=np.complex128),
                port_rhs=np.ones(2, dtype=np.complex128),
            ),
        )
        np.testing.assert_array_equal(
            p4.recover_storage(x, full_rhs=np.ones(4, dtype=np.complex128)),
            old.recover_storage(x, full_rhs=np.ones(4, dtype=np.complex128)),
        )
        assert p4.audit["matrix_materialized"] is True
        assert p4.audit["borrowed_p4_schur_witness"] is True
        assert p4._cells[0].S_V is old._cells[0].S_V
        p4.destroy()
        assert condensed.matrix is materialized and materialized.getSize() == (4, 4)
        condensed.build_audit["local_tensor_dimension"] = 882
        with pytest.raises(ValueError, match="only caller-owned"):
            P6CellCondensedAction(condensed, H_p=old.H_p, borrowed_p4_witness=True)
    finally:
        if p4 is not None:
            p4.destroy()
        old.destroy()
        materialized.destroy()
