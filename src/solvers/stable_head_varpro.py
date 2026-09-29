"""Stable, fixed-threshold neural output head over the original Schur action.

The only inverse is the original forty-by-forty condensed port block.  QR and
GELSD act on tall, thin feature matrices; no global FE matrix is assembled.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import numpy as np

RANK_TOL = 1e-12
HEAD_COLUMNS = 1560
PORT_COLUMNS = 40


def rhs_residual(packet, z, rhs):
    """Schur audit for an explicitly supplied RHS; never substitutes physical b."""
    rhs = np.asarray(rhs, dtype=np.complex128)
    z = np.asarray(z, dtype=np.complex128)
    if rhs.shape != (packet.size,) or z.shape != (packet.size,):
        raise ValueError("complete canonical trace and forty-port inventory required")
    if not np.isfinite(rhs).all() or not np.isfinite(z).all():
        raise ValueError("nonfinite manufactured state/RHS")
    residual = rhs - packet.apply(z)
    return {
        "absolute": float(np.linalg.norm(residual)),
        "relative": float(np.linalg.norm(residual) / max(np.linalg.norm(rhs), 1e-300)),
        "port_absolute": float(np.linalg.norm(residual[packet.nt :])),
        "rhs_trace_norm": float(np.linalg.norm(rhs[: packet.nt])),
        "rhs_port_norm": float(np.linalg.norm(rhs[packet.nt :])),
    }


def homogeneous_recovery_pair(packet, z_reference, z_candidate):
    """Compare F(z_ref)-F(z) with F(e)-F(0), cancelling internal particular RHS."""
    zero = np.zeros(packet.size, np.complex128)
    field_reference = packet.recover(z_reference)
    field_candidate = packet.recover(z_candidate)
    field_error = packet.recover(z_reference - z_candidate)
    field_zero = packet.recover(zero)
    difference = field_reference - field_candidate
    homogeneous = field_error - field_zero
    scale = max(np.linalg.norm(field_reference) + np.linalg.norm(field_candidate),
                np.linalg.norm(field_error) + np.linalg.norm(field_zero), 1e-300)
    return float(np.linalg.norm(difference - homogeneous) / scale)


@dataclass
class PortBlocks:
    packet: object
    columns: np.ndarray

    def __post_init__(self):
        if self.packet.np != PORT_COLUMNS or self.columns.shape != (self.packet.size, PORT_COLUMNS):
            raise ValueError("all original forty port columns required")
        self.H = self.packet.a["Hhat"]
        self.C = self.columns[: self.packet.nt]
        self.cond_H = float(np.linalg.cond(self.H))
        if not np.isfinite(self.cond_H) or self.cond_H > 1e10:
            raise ValueError("PORT_BLOCK_UNSAFE")
        self.port_column_pair = float(
            np.linalg.norm(self.columns[self.packet.nt :] - self.H)
            / max(np.linalg.norm(self.H), 1e-300)
        )
        if self.port_column_pair > 1e-10:
            raise ValueError("Hhat and original port columns differ")

    def reduced_rhs(self, rhs):
        return rhs[: self.packet.nt] - self.C @ np.linalg.solve(self.H, rhs[self.packet.nt :])

    def closed(self, trace, rhs):
        zero = np.zeros(PORT_COLUMNS, np.complex128)
        action = self.packet.apply(np.r_[trace, zero])
        alpha = np.linalg.solve(self.H, rhs[self.packet.nt :] - action[self.packet.nt :])
        return np.r_[trace, alpha], action

    def adjoint(self, residual):
        """bar S^H r = K^H r - F^H H^{-H} C^H r, including original signs."""
        zero = np.zeros(PORT_COLUMNS, np.complex128)
        first = self.packet.apply(np.r_[residual, zero], adjoint=True)
        dual = np.linalg.solve(self.H.conj().T, first[self.packet.nt :])
        second = self.packet.apply(
            np.r_[np.zeros(self.packet.nt, np.complex128), dual], adjoint=True
        )
        return first[: self.packet.nt] - second[: self.packet.nt]


class StableBasis:
    """One hidden feature space; reuse its QR/A for multiple explicitly named RHS."""

    def __init__(self, packet, P, ports, *, heartbeat=None):
        from scipy.linalg import qr, svdvals

        if P.shape != (packet.nt, HEAD_COLUMNS) or P.dtype != np.complex128:
            raise ValueError("reviewed complex128 P inventory required")
        self.packet = packet
        self.P = P
        self.ports = PortBlocks(packet, ports)
        self.times = {}
        t0 = perf_counter()
        self.Z, self.R = qr(P, mode="economic", pivoting=False, check_finite=False)
        self.times["P_economic_householder_qr"] = perf_counter() - t0
        self.P_reassembly = float(
            np.linalg.norm(P - self.Z @ self.R) / max(np.linalg.norm(P), 1e-300)
        )
        gram = self.Z.conj().T @ self.Z
        gram.flat[:: HEAD_COLUMNS + 1] -= 1
        self.Z_orthogonality = float(np.linalg.norm(gram) / np.sqrt(HEAD_COLUMNS))
        del gram
        p_s = svdvals(self.R, check_finite=False)
        self.P_rank = int(np.count_nonzero(p_s > RANK_TOL * p_s[0]))
        self.P_singular_range = [float(p_s[-1]), float(p_s[0])]
        if self.P_reassembly > 1e-10 or self.Z_orthogonality > 1e-10:
            raise ValueError("P QR reconstruction/orthogonality failed")
        if self.P_rank != HEAD_COLUMNS:
            raise ValueError("HEAD_RANK_UNSAFE_FOR_VARPRO: P")
        self.A = np.empty((packet.nt, HEAD_COLUMNS), np.complex128, order="F")
        zero = np.zeros(PORT_COLUMNS, np.complex128)
        t0 = perf_counter()
        for start in range(0, HEAD_COLUMNS, 16):
            stop = min(start + 16, HEAD_COLUMNS)
            action = np.column_stack(
                [packet.apply(np.r_[self.Z[:, j], zero]) for j in range(start, stop)]
            )
            self.A[:, start:stop] = action[: packet.nt] - self.ports.C @ np.linalg.solve(
                self.ports.H, action[packet.nt :]
            )
            if heartbeat is not None and (stop % 128 == 0 or stop == HEAD_COLUMNS):
                heartbeat("stable_A_columns", completed=stop, total=HEAD_COLUMNS)
        self.times["fresh_original_S_on_Z"] = perf_counter() - t0
        # Economic QR of A gives the actual Euclidean residual projection test.
        t0 = perf_counter()
        self.U, self.RA = qr(self.A, mode="economic", pivoting=False, check_finite=False)
        self.times["A_economic_qr_for_stationarity"] = perf_counter() - t0

    def solve(self, rhs):
        from scipy.linalg import lstsq, solve_triangular

        if rhs.shape != (self.packet.size,):
            raise ValueError("complete independent RHS required")
        barb = self.ports.reduced_rhs(rhs)
        t0 = perf_counter()
        c, _, rank, singular = lstsq(
            self.A, barb, cond=RANK_TOL, lapack_driver="gelsd", check_finite=False
        )
        ls_seconds = perf_counter() - t0
        gamma = solve_triangular(self.R, c, lower=False, check_finite=False)
        trace_p = self.P @ gamma
        trace_z = self.Z @ c
        z, action = self.ports.closed(trace_p, rhs)
        actual_r = barb - (action[: self.packet.nt] - self.ports.C @ np.linalg.solve(
            self.ports.H, action[self.packet.nt :]
        ))
        projected_r = barb - self.A @ c
        full_r = rhs - self.packet.apply(z)
        return {
            "gamma": gamma,
            "alpha": z[self.packet.nt :],
            "trace_p": trace_p,
            "trace_z": trace_z,
            "bar_residual": actual_r,
            "bar_rhs": barb,
            "rank_A": int(rank),
            "A_singular_range": [float(singular[-1]), float(singular[0])],
            "numerical_full_column_rank": bool(rank == HEAD_COLUMNS),
            "least_squares_seconds": ls_seconds,
            "trace_P_vs_Z_relative": float(
                np.linalg.norm(trace_p - trace_z)
                / max(np.linalg.norm(trace_z), np.linalg.norm(trace_p), 1e-300)
            ),
            "actual_vs_thin_residual_fixed_rhs": float(
                np.linalg.norm(actual_r - projected_r)
                / max(np.linalg.norm(rhs), 1e-300)
            ),
            "stationarity_UHr_fixed_rhs": float(
                np.linalg.norm(self.U.conj().T @ actual_r)
                / max(np.linalg.norm(rhs), 1e-300)
            ),
            "AHr_absolute": float(np.linalg.norm(self.A.conj().T @ actual_r)),
            "Schur_relative": float(np.linalg.norm(full_r) / max(np.linalg.norm(rhs), 1e-300)),
            "port_absolute": float(np.linalg.norm(full_r[self.packet.nt :])),
        }


def lbfgs_direction(gradient, history):
    """Hidden-only, real L-BFGS with at most five accepted curvature pairs."""
    q = gradient.copy()
    alpha = []
    for s, y in reversed(history[-5:]):
        rho = 1.0 / float(np.dot(s, y))
        a = rho * float(np.dot(s, q))
        alpha.append(a)
        q -= a * y
    if history:
        s, y = history[-1]
        q *= float(np.dot(s, y) / np.dot(y, y))
    for (s, y), a in zip(history[-5:], reversed(alpha)):
        rho = 1.0 / float(np.dot(s, y))
        q += s * (a - rho * float(np.dot(y, q)))
    direction = -q
    if not np.isfinite(direction).all() or np.dot(direction, gradient) >= 0:
        direction = -gradient.copy()
    return direction


def armijo_steps(hidden, direction):
    if np.linalg.norm(direction) == 0 or not np.isfinite(direction).all():
        raise ValueError("no finite descent direction")
    alpha0 = min(1.0, 1e-3 * max(1.0, np.linalg.norm(hidden)) / np.linalg.norm(direction))
    return [alpha0 * 4.0 ** -j for j in range(4)]


def one_same_basis_residual_correction(
    packet, P, A, ports, old_gamma, actual_bar_residual, *, qr_cache=None
):
    """Exactly one GELSD correction against a saved A from the same frozen P.

    Recomputing P's deterministic economic QR supplies only its triangular R.
    The expensive A is read unchanged; three original actions verify that the
    recomputed Z still corresponds to that saved A.  No second correction loop.
    """
    from scipy.linalg import lstsq, qr, solve_triangular

    if P.shape != (packet.nt, HEAD_COLUMNS) or A.shape != (packet.nt, HEAD_COLUMNS):
        raise ValueError("same-space correction input shape mismatch")
    if qr_cache is None:
        Z, R = qr(P, mode="economic", pivoting=False, check_finite=False)
        reassembly = float(np.linalg.norm(P - Z @ R) / max(np.linalg.norm(P), 1e-300))
        if reassembly > 1e-10:
            raise ValueError("same-space QR reconstruction failed")
        checks = []
        for j in (0, HEAD_COLUMNS // 2, HEAD_COLUMNS - 1):
            action = packet.apply(np.r_[Z[:, j], np.zeros(PORT_COLUMNS, np.complex128)])
            actual = action[: packet.nt] - ports.C @ np.linalg.solve(ports.H, action[packet.nt :])
            checks.append(float(np.linalg.norm(actual - A[:, j]) / max(np.linalg.norm(A[:, j]), 1e-300)))
        if max(checks) > 1e-10:
            raise ValueError("saved A does not match same deterministic QR space")
        qr_cache = (Z, R, reassembly, checks)
    else:
        Z, R, reassembly, checks = qr_cache
    delta_c, _, rank, singular = lstsq(
        A, actual_bar_residual, cond=RANK_TOL, lapack_driver="gelsd", check_finite=False
    )
    if rank != HEAD_COLUMNS:
        raise ValueError("saved A rank unsafe for correction")
    delta_gamma = solve_triangular(R, delta_c, lower=False, check_finite=False)
    gamma = old_gamma + delta_gamma
    return gamma, Z @ delta_c, A @ delta_c, {
        "same_space_P_reassembly": reassembly,
        "saved_A_three_fresh_original_action_checks": checks,
        "rank_A": int(rank),
        "A_singular_range": [float(singular[-1]), float(singular[0])],
        "delta_c_norm": float(np.linalg.norm(delta_c)),
        "delta_gamma_norm": float(np.linalg.norm(delta_gamma)),
        "one_correction_only": True,
        "new_global_factor_constructed": False,
    }, qr_cache
