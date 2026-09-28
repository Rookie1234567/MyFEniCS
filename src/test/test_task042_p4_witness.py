"""Small algebraic adapter checks, native PETSc ABI only, no mesh/forms/JIT."""

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.p6_cell_condensed_action import P6CellCondensedAction
from src.test.test_task039extra_v20_noncommuting_contract import _problem


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
