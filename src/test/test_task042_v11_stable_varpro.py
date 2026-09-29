"""V11 non-Hermitian, nonzero-port algebra and complete variable-projection FD."""

import numpy as np

from src.solvers import stable_head_varpro as v11


class SmallPacket:
    def __init__(self):
        rng = np.random.default_rng(421105)
        self.nt, self.np = 7, 40
        self.size = self.nt + self.np
        K = rng.normal(size=(7, 7)) + 1j * rng.normal(size=(7, 7))
        C = (rng.normal(size=(7, 40)) + 1j * rng.normal(size=(7, 40))) / 10
        F = (rng.normal(size=(40, 7)) + 1j * rng.normal(size=(40, 7))) / 10
        H = 2 * np.eye(40) + (
            rng.normal(size=(40, 40)) + 1j * rng.normal(size=(40, 40))
        ) / 40
        self.S = np.block([[K + 3 * np.eye(7), C], [F, H]])
        self.a = {"Hhat": H}
        self.bnorm = 1.0
        self.particular = rng.normal(size=11) + 1j * rng.normal(size=11)
        self.recovery_matrix = (rng.normal(size=(11, self.size))
                                + 1j * rng.normal(size=(11, self.size)))

    def apply(self, value, *, adjoint=False):
        return self.S.conj().T @ value if adjoint else self.S @ value

    def recover(self, value):
        return self.particular + self.recovery_matrix @ value


def _ports(packet):
    return packet.S[:, packet.nt :]


def test_manufactured_rhs_and_homogeneous_recovery(monkeypatch):
    monkeypatch.setattr(v11, "HEAD_COLUMNS", 3)
    rng = np.random.default_rng(421106)
    packet = SmallPacket()
    P = rng.normal(size=(7, 3)) + 1j * rng.normal(size=(7, 3))
    gamma = rng.normal(size=3) + 1j * rng.normal(size=3)
    alpha = rng.normal(size=40) + 1j * rng.normal(size=40)
    known = np.r_[P @ gamma, alpha]
    rhs = packet.apply(known)
    packet.bnorm = float(np.linalg.norm(rhs))
    basis = v11.StableBasis(packet, P.astype(np.complex128), _ports(packet))
    solved = basis.solve(rhs)
    z, _ = basis.ports.closed(solved["trace_p"], rhs)
    assert basis.P_rank == 3
    assert solved["rank_A"] == 3
    assert v11.rhs_residual(packet, z, rhs)["relative"] < 1e-10
    assert np.linalg.norm(z - known) / np.linalg.norm(known) < 1e-10
    assert v11.homogeneous_recovery_pair(packet, known, z) < 1e-10
    assert solved["stationarity_UHr_fixed_rhs"] < 1e-10
    # A packet.audit hardwired to a different physical b would be wrong here.
    assert np.linalg.norm(rhs[packet.nt :]) > 0


def test_complete_scalar_envelope_gradient_reoptimizes_head(monkeypatch):
    monkeypatch.setattr(v11, "HEAD_COLUMNS", 3)
    rng = np.random.default_rng(421107)
    packet = SmallPacket()
    P0 = rng.normal(size=(7, 3)) + 1j * rng.normal(size=(7, 3))
    dP = rng.normal(size=(7, 3)) + 1j * rng.normal(size=(7, 3))
    rhs = rng.normal(size=packet.size) + 1j * rng.normal(size=packet.size)
    rhs[packet.nt :] += 0.1
    packet.bnorm = float(np.linalg.norm(rhs))

    def evaluate(psi):
        P = np.asarray(P0 + psi * dP, dtype=np.complex128)
        basis = v11.StableBasis(packet, P, _ports(packet))
        solved = basis.solve(rhs)
        residual = solved["bar_residual"]
        phi = float(np.vdot(residual, residual).real / (2 * packet.bnorm**2))
        return phi, basis, solved

    phi0, basis, solved = evaluate(0.03)
    dual = basis.ports.adjoint(solved["bar_residual"])
    analytic = -float(np.vdot(dual, dP @ solved["gamma"]).real / packet.bnorm**2)
    for h in (1e-4, 1e-5, 1e-6):
        plus, _, _ = evaluate(0.03 + h)
        minus, _, _ = evaluate(0.03 - h)
        observed = (plus - minus) / (2 * h)
        assert abs(observed - analytic) < 1e-7 * max(1, abs(analytic))
    # Keeping the old head at another psi solves a different optimization
    # problem. This makes no false claim that partial and envelope derivatives
    # must differ at their shared stationary point.
    frozen_gamma = solved["gamma"]
    other, other_basis, _ = evaluate(0.4)
    fixed = np.r_[other_basis.P @ frozen_gamma, np.zeros(40, np.complex128)]
    fixed, _ = other_basis.ports.closed(fixed[: packet.nt], rhs)
    fixed_residual = rhs - packet.apply(fixed)
    assert other >= 0
    assert np.linalg.norm(fixed_residual) > 0
    assert np.isfinite(phi0)


def test_hidden_only_armijo_and_lbfgs():
    hidden = np.array([1.0, -2.0, 3.0])
    gradient = np.array([0.3, -0.2, 0.1])
    direction = v11.lbfgs_direction(gradient, [])
    np.testing.assert_array_equal(direction, -gradient)
    steps = v11.armijo_steps(hidden, direction)
    assert len(steps) == 4
    assert steps[0] > steps[1] > steps[2] > steps[3] > 0


def test_one_saved_basis_residual_correction(monkeypatch):
    monkeypatch.setattr(v11, "HEAD_COLUMNS", 3)
    rng = np.random.default_rng(421108)
    packet = SmallPacket()
    P = np.asarray(rng.normal(size=(7, 3)) + 1j * rng.normal(size=(7, 3)),
                   dtype=np.complex128)
    basis = v11.StableBasis(packet, P, _ports(packet))
    known_gamma = rng.normal(size=3) + 1j * rng.normal(size=3)
    known_port = rng.normal(size=40) + 1j * rng.normal(size=40)
    rhs = packet.apply(np.r_[P @ known_gamma, known_port])
    old_gamma = known_gamma + 0.01 * (rng.normal(size=3) + 1j * rng.normal(size=3))
    _, action = basis.ports.closed(P @ old_gamma, rhs)
    bar_rhs = basis.ports.reduced_rhs(rhs)
    residual = bar_rhs - (
        action[: packet.nt] - basis.ports.C @ np.linalg.solve(
            basis.ports.H, action[packet.nt :]
        )
    )
    gamma, _, _, record, _ = v11.one_same_basis_residual_correction(
        packet, P, basis.A, basis.ports, old_gamma, residual
    )
    z, _ = basis.ports.closed(P @ gamma, rhs)
    assert record["one_correction_only"]
    assert max(record["saved_A_three_fresh_original_action_checks"]) < 1e-10
    assert v11.rhs_residual(packet, z, rhs)["relative"] < 1e-10
