"""The approximate interface inverse uses the inexact BAL_H identity."""

import numpy as np
import pytest
from petsc4py import PETSc

from src.solvers.physical_balanced_coupling import BalancedConstraintRejected
from src.solvers.physical_interface_balanced import InterfaceBalancedCoupling


def _vector(values):
    result = PETSc.Vec().createSeq(len(values), comm=PETSc.COMM_SELF)
    result.array[:] = values
    return result


@pytest.mark.parametrize('incorrect_p4_action', [False, True])
def test_actual_feedback_and_eps_difference_for_approximate_fint(incorrect_p4_action):
    A6 = np.array([[3.+1j, 1., -.2j], [.4j, 2., .5], [.2, .3j, 4.-1j]])
    P = np.array([[1., 0.], [.3j, .8], [0., 1.]], dtype=complex)
    A4 = P.conj().T @ A6 @ P
    F = np.diag([.1, .15]).astype(complex)
    H6 = np.diag([.2, .25, .1]).astype(complex)
    q_values = np.array([1.+.2j, -.3j, 2.-1j])

    class Transfer:
        def apply_primal(self, source):
            return _vector(P @ source.array)

        def apply_adjoint(self, source):
            return _vector(P.conj().T @ source.array)

    class Fint:
        def __init__(self):
            self.inputs = []

        def apply_with_facts(self, source):
            self.inputs.append(source.array.copy())
            return _vector(F @ source.array), {'inner_iteration_count': 0}

    fint = Fint()
    A4_used = A4 + (.25*np.eye(2) if incorrect_p4_action else 0)
    pc = InterfaceBalancedCoupling(
        lambda x: _vector(A6 @ x.array), lambda x: _vector(A4_used @ x.array),
        Transfer(), fint, lambda x: _vector(H6 @ x.array),
        save=lambda *_args: None, capture_vectors=True)
    q = _vector(q_values)
    z = None
    try:
        if incorrect_p4_action:
            with pytest.raises(BalancedConstraintRejected):
                pc.apply(q)
            return
        z = pc.apply(q)
        g1 = P.conj().T @ q_values
        c1 = F @ g1
        s = H6 @ (q_values - A6 @ P @ c1)
        g2 = P.conj().T @ A6 @ s
        c2 = F @ g2
        expected_z = P @ c1 + s - P @ c2
        np.testing.assert_allclose(z.array, expected_z, atol=1e-13)
        np.testing.assert_allclose(fint.inputs[1], g2, atol=1e-13)
        np.testing.assert_allclose(pc.ledger.last['difference'].array,
                                   (g1-A4@c1)-(g2-A4@c2), atol=1e-13)
        closure = pc.last_apply_facts['inexact_balance']['audit']
        assert closure['closure_relative'] <= 1e-8
        assert closure['actual_defect_norm'] > .01  # Approximate PC is legal.
        assert pc.native_A4_count == 2
        assert pc.ledger.A_count == pc.ledger.PH_count == 1
        assert pc.last_apply_facts['counts'] == {
            'C': 2, 'smoother': 1, 'A_structure': 2, 'A_inner_true': 0, 'PH_audit': 0}
        np.testing.assert_array_equal(q.array, q_values)
        saved_calls = pc.coarse_calls
        pc.destroy()
        assert len(saved_calls) == 2
        assert not pc.last_apply_vectors
    finally:
        if z is not None:
            z.destroy()
        pc.destroy()
        q.destroy()
