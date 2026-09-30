"""V12 fixed-head derivative/closure and bounded acceptance tests."""

import numpy as np

from src.runners.actual_loss_block_descent import synthetic_fixed_head_check
from src.solvers.actual_loss_block_descent import (
    FixedHeadObjective, actual_loss, armijo_accept, resolution, trial_steps,
)
from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.stable_head_varpro import PortBlocks


class DensePacket:
    def __init__(self, matrix, rhs):
        self.matrix = matrix
        self.a = {"Hhat": matrix[-40:, -40:], "b": rhs}
        self.nt = len(rhs)-40
        self.np = 40
        self.size = len(rhs)

    def apply(self, value, *, adjoint=False):
        return (self.matrix.conj().T if adjoint else self.matrix) @ value


def test_nonstationary_fixed_head_complex_gradient():
    row = synthetic_fixed_head_check()
    assert row["qualified"] and row["non_Hermitian"] and row["nonzero_port"]
    assert row["relative"] < 1e-7


def test_original_port_closure_and_adjoint_on_same_complex_vector():
    rng = np.random.default_rng(421206)
    n = 43
    matrix = rng.standard_normal((n, n)) + 1j*rng.standard_normal((n, n))
    matrix[-40:, -40:] = np.eye(40)*(2+0.1j)
    rhs = rng.standard_normal(n) + 1j*rng.standard_normal(n)
    packet = DensePacket(matrix, rhs)
    ports = PortBlocks(packet, matrix[:, 3:])
    trace = rng.standard_normal(3) + 1j*rng.standard_normal(3)
    row = actual_loss(packet, ports, trace, rhs)
    residual = rhs-matrix @ row["z"]
    assert np.linalg.norm(residual[-40:])/np.linalg.norm(rhs) < 1e-13
    bar = matrix[:3,:3]-matrix[:3,3:] @ np.linalg.solve(matrix[3:,3:],matrix[3:,:3])
    dual = rng.standard_normal(3)+1j*rng.standard_normal(3)
    assert np.linalg.norm(ports.adjoint(dual)-bar.conj().T @ dual) < 1e-12
    bar_rhs = ports.reduced_rhs(rhs)
    assert abs(row["loss"]-np.vdot(bar_rhs-bar@trace,bar_rhs-bar@trace).real/(2*np.vdot(rhs,rhs).real)) < 1e-12


def test_hidden_assignment_restores_exact_same_head():
    from src.solvers.neural_linear_head_torch import head_coefficients
    from src.solvers.neural_trace_torch import NeuralTrace
    from src.solvers.stable_head_varpro_torch import hidden_vector

    model = NeuralTrace(np.array([[0,1],[0,1],[0,1]]), 0.7, seed=420906)
    objective = FixedHeadObjective(DensePacket(np.eye(41,dtype=np.complex128),
                                                 np.ones(41,dtype=np.complex128)),
                                   None, model, None, np.ones(41,dtype=np.complex128))
    hidden = hidden_vector(model)
    gamma = np.arange(1560)/1560 + 1j*np.arange(1560)[::-1]/1560
    expected = array_hash(gamma.astype(np.complex128))
    for offset in (0., 1e-5):
        assert objective.assign(hidden+offset, gamma) == expected
        assert array_hash(head_coefficients(model)) == expected


def test_armijo_uses_actual_loss_and_resolution_margin():
    hidden=np.ones(8576)
    direction=-np.ones(8576)
    steps=trial_steps(hidden,direction)
    assert len(steps)==8 and np.isclose(steps[1],steps[0]/4)
    assert armijo_accept(1.,.9,steps[0],-1.,1e-14)
    assert not armijo_accept(1.,1.,steps[0],-1.,1e-14)
    assert not armijo_accept(1.,.999999999999,steps[0],-1.,1e-9)
    assert resolution([1.,1.,1.]) >= 100*np.finfo(np.float64).eps
