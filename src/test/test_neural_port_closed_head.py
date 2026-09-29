"""Exact non-Hermitian small port elimination and true complex chain rule."""

import numpy as np

from src.solvers.neural_port_closed_head import (
    close_ports,
    closed_trace_gradient,
    real_port_algebra,
    safe_Hhat,
    solve_closed_head,
)


class Packet:
    def __init__(self):
        rng = np.random.default_rng(421031)
        self.nt = 12
        self.size = 52
        self.matrix = rng.normal(size=(52, 52)) + 1j * rng.normal(size=(52, 52))
        self.matrix[12:, 12:] += 50 * np.eye(40)
        self.a = {
            "Hhat": self.matrix[12:, 12:],
            "b": rng.normal(size=52) + 1j * rng.normal(size=52),
        }
        self.bnorm = np.linalg.norm(self.a["b"])

    def apply(self, value, adjoint=False):
        return (self.matrix.conj().T if adjoint else self.matrix) @ value


def test_original_nonhermitian_blocks_and_real_gradient():
    packet = Packet()
    checks = real_port_algebra(packet, packet.matrix[:, packet.nt :])
    assert checks["status"] == "PASS"
    assert checks["gradient_nonzero_norm"] > 0
    assert all(item["passed"] for item in checks["true_original_gradient_fd"])
    trace = np.arange(packet.nt) * (0.02 + 0.01j)
    z, _ = close_ports(packet, trace)
    assert np.linalg.norm((packet.a["b"] - packet.apply(z))[packet.nt :]) < 1e-13
    _, _, gradient, _ = closed_trace_gradient(packet, z)
    assert np.isfinite(gradient).all()
    assert (
        safe_Hhat(np.diag(np.r_[np.ones(39), 1e-14]))["status"] == "PORT_BLOCK_UNSAFE"
    )


def test_closed_trace_ls_retains_all_original_ports():
    packet = Packet()
    rng = np.random.default_rng(421032)
    P = rng.normal(size=(12, 6)) + 1j * rng.normal(size=(12, 6))
    Q = np.zeros((52, 46), complex)
    Q[:12, :6] = P
    Q[12:, 6:] = np.eye(40)
    W = packet.matrix @ Q
    gamma, z, record = solve_closed_head(packet, P, W, np.zeros(6, complex))
    assert record["all_ports_retained"] == 40
    assert record["effective_rank"] == 6
    assert np.allclose(P @ gamma, z[:12])
    assert np.linalg.norm((packet.a["b"] - packet.apply(z))[12:]) < 1e-13
    assert not record["full_K_minus_C_Hinv_F_constructed"]
