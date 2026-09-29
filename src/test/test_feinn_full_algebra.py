"""Non-Hermitian full-space algebra; independent small explicit witnesses."""

import numpy as np
import pytest

from src.solvers.feinn_native import FullNativePacket, ResidualMetric


def fixture_packet():
    rng = np.random.default_rng(421002)

    def random(shape):
        return rng.standard_normal(shape) + 1j * rng.standard_normal(shape)

    arrays = dict(
        F=random((2, 3, 3)),
        classes=np.arange(2),
        cell_dofs=np.array([[0, 1, 4], [2, 3, 5]]),
        masters=np.arange(4),
        slaves=np.array([4, 5]),
        full_rows=np.asarray(6),
        erows=np.arange(6),
        eids=np.array([0, 1, 2, 2, 3, 0]),
        evals=np.array([1, 1, np.exp(0.2j), 1, 1, np.exp(0.3j)]),
        br=np.repeat(np.arange(4), 2),
        bp=np.tile(np.arange(2), 4),
        bv=random(8),
        dr=np.repeat(np.arange(4), 2),
        dp=np.tile(np.arange(2), 4),
        dv=random(8),
        H=np.array([0.7, 1.3]),
        g=random(4),
        gp=random(2),
        idofs=np.array([2, 3]),
        background=np.zeros(4, dtype=complex),
        background_alpha=np.zeros(2, dtype=complex),
        total_g=random(4),
    )
    return FullNativePacket(arrays)


def test_original_port_elimination_and_adjoint():
    packet = fixture_packet()
    a = packet.a
    E = np.zeros((6, 4), dtype=complex)
    E[a["erows"], a["eids"]] = a["evals"]
    V = (
        E.conj().T
        @ np.block([[a["F"][0], np.zeros((3, 3))], [np.zeros((3, 3)), a["F"][1]]])
        @ E
    )
    B = np.zeros((4, 2), dtype=complex)
    B[a["br"], a["bp"]] = a["bv"]
    D = np.zeros((2, 4), dtype=complex)
    D[a["dp"], a["dr"]] = a["dv"]
    A = V + B @ np.linalg.solve(np.diag(a["H"]), D)
    assert np.linalg.norm(A - A.conj().T) > 1
    rng = np.random.default_rng(3)
    for _ in range(3):
        c = rng.standard_normal(4) + 1j * rng.standard_normal(4)
        np.testing.assert_allclose(packet.apply(c), A @ c, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(
            packet.apply(c, adjoint=True), A.conj().T @ c, rtol=1e-12, atol=1e-12
        )
        alpha = np.linalg.solve(np.diag(a["H"]), a["gp"] + D @ c)
        np.testing.assert_allclose(packet.alpha(c), alpha, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(
            V @ c + B @ alpha - a["g"],
            packet.apply(c) - packet.f,
            rtol=1e-12,
            atol=1e-12,
        )
    assert np.linalg.norm(B - D.conj().T) > 1


@pytest.mark.parametrize("dual", [False, True])
def test_real_complex_gradient_half_normalization(dual):
    packet = fixture_packet()
    rng = np.random.default_rng(8)
    M = rng.standard_normal((4, 4)) + 1j * rng.standard_normal((4, 4))
    G = M.conj().T @ M + np.eye(4)

    class Gram:
        def solve(self, rhs):
            return np.linalg.solve(G, rhs)

    metric = ResidualMetric(packet, Gram() if dual else None)
    c = rng.standard_normal(4) + 1j * rng.standard_normal(4)
    loss, _, gradient = metric.value(c, gradient=True)
    assert loss > 0
    for _ in range(3):
        d = rng.standard_normal(4) + 1j * rng.standard_normal(4)
        fd = (metric.value(c + 1e-5 * d)[0] - metric.value(c - 1e-5 * d)[0]) / 2e-5
        assert abs(fd - np.vdot(d, gradient).real) < 1e-7


def test_dtype_shape_nan_and_zero_rhs_fail_closed():
    packet = fixture_packet()
    for value in (np.zeros(4), np.zeros(5, dtype=complex), np.full(4, np.nan + 0j)):
        with pytest.raises(ValueError):
            packet.apply(value)
    with pytest.raises(ValueError):
        FullNativePacket(
            dict(packet.a, g=np.zeros(4, dtype=complex), gp=np.zeros(2, dtype=complex))
        )
