"""Complex nonsymmetric cell elimination with dense Floquet pullbacks."""

import numpy as np

from src.geometry.neural_micro_pilot import hexa_inventory
from src.solvers.neural_fe_action_packet import ActionPacket, capacity_before_allocation


def witness():
    rng = np.random.default_rng(58)

    def random(shape):
        return rng.standard_normal(shape) + 1j * rng.standard_normal(shape)

    F = random((3, 3)) + 5 * np.eye(3)
    E = np.array([[1, 0.25j], [0.2 - 0.3j, np.exp(0.17j)]])
    Bt, Bi, Dt, Di = random((2, 2)), random((1, 2)), random((2, 2)), random((2, 1))
    Hp = random((2, 2)) + 4 * np.eye(2)
    R, Q = -F[2:, :2] / F[2, 2], -F[:2, 2:] / F[2, 2]
    S = F[:2, :2] + F[:2, 2:] @ R
    XiB = Bi / F[2, 2]
    g = random(3)
    gp = random(2)
    b = np.r_[g[:2] + E.conj().T @ (Q @ g[2:]), gp + Di @ g[2:] / F[2, 2]]
    e = E.nonzero()
    a = dict(
        S=S[None],
        F=F[None],
        R=R[None],
        classes=np.array([0]),
        tdofs=np.array([[0, 1]]),
        idofs=np.array([[2]]),
        masters=np.array([0, 1]),
        slaves=np.array([], dtype=int),
        full_rows=np.array(3),
        Hp=Hp,
        Hhat=Hp + Di @ XiB,
        g=g,
        gp=gp,
        b=b,
        i_rhs=(g[2:] / F[2, 2])[None],
        background=np.zeros(3, complex),
        background_alpha=np.zeros(2, complex),
        total_g=g.copy(),
        tpositions=np.array([0, 1]),
        ipositions=np.array([2]),
        erows=e[0],
        eids=e[1],
        evals=E[e],
        Bt=Bt[None],
        Bi=Bi[None],
        Dt=Dt[None],
        Di=Di[None],
        XiB=XiB[None],
        Bhat=(Bt + Q @ Bi)[None],
        Dhat=(Dt + Di @ R)[None],
        br=np.array([0]),
        bp=np.array([1]),
        bv=np.array([0.4 + 0.7j]),
        dr=np.array([1]),
        dp=np.array([0]),
        dv=np.array([-0.3 + 0.9j]),
    )
    matrix = np.block(
        [
            [E.conj().T @ S @ E, E.conj().T @ (Bt + Q @ Bi)],
            [-(Dt + Di @ R) @ E, Hp + Di @ XiB],
        ]
    )
    matrix[0, 3] += a["bv"][0]
    matrix[2, 1] -= a["dv"][0]
    return ActionPacket(a), matrix, F, E, Bt, Bi, Dt, Di, Hp


def test_complex_adjoint_and_original_equations():
    packet, S, F, E, Bt, Bi, Dt, Di, Hp = witness()
    x = np.array([1.3 + 0.4j, 0.1 - 0.8j, 0.2 + 0.3j, 0.7 - 0.5j])
    y = x[::-1] * (-0.9j)
    np.testing.assert_allclose(packet.apply(x), S @ x, rtol=1e-13, atol=1e-13)
    np.testing.assert_allclose(
        packet.apply(y, adjoint=True), S.conj().T @ y, rtol=1e-13, atol=1e-13
    )
    assert (
        abs(np.vdot(y, packet.apply(x)) - np.vdot(packet.apply(y, adjoint=True), x))
        < 1e-12
    )
    field = packet.recover(x)
    local = np.r_[E @ x[:2], field[2]]
    expected = F @ local + np.vstack([Bt, Bi]) @ x[2:]
    af, rp, Df = packet.uncondensed(field, x[2:])
    full = np.r_[E.conj().T @ expected[:2], expected[2]]
    full[0] += packet.a["bv"][0] * x[3]
    port = Dt @ (E @ x[:2]) + Di @ field[2:]
    port[0] += packet.a["dv"][0] * x[1]
    np.testing.assert_allclose(af, full, rtol=1e-13, atol=1e-13)
    np.testing.assert_allclose(Df, port, rtol=1e-13, atol=1e-13)
    np.testing.assert_allclose(rp, port - Hp @ x[2:], rtol=1e-13, atol=1e-13)
    audit = packet.audit(x)
    assert audit["schur_original_identity_operation_relative"] < 1e-13
    assert audit["recovery_relative"] < 1e-13


def test_capacity_includes_original_cell_audit_and_temporary_copies():
    result = capacity_before_allocation(hexa_inventory((8, 6, 8), 3), 40)
    assert 4 * 2**30 < result["total_upper_bytes"] < 12 * 2**30
    assert not result["private_audit_CSR"] and not result["global_p4_factor"]
