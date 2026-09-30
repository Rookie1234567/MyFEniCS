"""Bounded complex G-QR readout projection; no inverse or normal equations."""

from time import perf_counter

import numpy as np

QR_TOL = 1e-12
SVD_RCOND = 1e-12


class ReadoutStop(RuntimeError):
    """A declared time or action budget, never a request to change method."""


class GramColumns:
    def __init__(self, G, limit=2500, deadline=float("inf")):
        self.G, self.limit, self.deadline = G, limit, deadline
        self.count, self.seconds, self.by_role = 0, 0.0, {}

    def check(self):
        if perf_counter() >= self.deadline:
            raise ReadoutStop("READOUT_SAVE_WINDOW_REACHED")

    def __call__(self, x, role):
        self.check()
        columns = 1 if x.ndim == 1 else x.shape[1]
        if self.count + columns > self.limit:
            raise ReadoutStop("READOUT_G_COLUMN_BUDGET")
        began = perf_counter()
        value = self.G @ x
        self.seconds += perf_counter() - began
        self.count += columns
        self.by_role[role] = self.by_role.get(role, 0) + columns
        if not np.isfinite(value).all():
            raise ValueError("READOUT_NONFINITE_G_ACTION")
        return value


def squared_norm(x, Gx):
    dot = np.vdot(x, Gx)
    if not np.isfinite(dot) or dot.real < 0:
        raise ValueError("READOUT_NONPOSITIVE_OR_NONFINITE_G_NORM")
    if abs(dot.imag) > 1e-10 * max(dot.real, 1e-300):
        raise ValueError("READOUT_NON_HERMITIAN_G_NORM")
    return float(dot.real)


def project(Phi, d, reference, action, heartbeat=lambda *_: None):
    """Column normalization, deterministic pivoted MGS2, small-R SVD.

    Cached G residuals select pivots; each selected residual is re-evaluated
    with actual G after both reorthogonalization passes. No squared-norm
    subtraction determines the stopping rank.
    """
    Phi = np.asarray(Phi, dtype=np.complex128)
    n, m = Phi.shape
    if d.shape != (n,) or reference.shape != (n,) or not np.isfinite(Phi).all():
        raise ValueError("READOUT_PROJECTION_SHAPE_OR_FINITE")
    GPhi = action(Phi, "column_normalization")
    scales = np.array([np.sqrt(squared_norm(Phi[:, j], GPhi[:, j])) for j in range(m)])
    zero = np.flatnonzero(scales == 0)
    nz = np.flatnonzero(scales > 0)
    U, GU = np.zeros_like(Phi), np.zeros_like(Phi)
    U[:, nz] = Phi[:, nz] / scales[nz]
    GU[:, nz] = GPhi[:, nz] / scales[nz]
    del GPhi
    V, GV = U.copy(), GU.copy()
    Q, GQ = np.empty((n, len(nz)), complex), np.empty((n, len(nz)), complex)
    remaining, pivots = list(nz), []
    rank = 0
    while remaining:
        action.check()
        norms = np.einsum("ij,ij->j", V[:, remaining].conj(), GV[:, remaining]).real
        # Cached tiny negative values receive a fresh action, never abs/epsilon.
        for pos in np.flatnonzero(norms < 0):
            j = remaining[pos]
            GV[:, j] = action(V[:, j], "negative_cached_norm_recheck")
            norms[pos] = squared_norm(V[:, j], GV[:, j])
        largest = np.max(norms)
        j = min(remaining[k] for k in np.flatnonzero(norms == largest))
        v = V[:, j].copy()
        gv = action(v, "selected_residual")
        for _ in range(2):
            if rank:
                h = Q[:, :rank].conj().T @ gv
                v -= Q[:, :rank] @ h
            gv = action(v, "reorthogonalized_residual")
        norm = np.sqrt(squared_norm(v, gv))
        if norm <= QR_TOL:
            # Verify all unresolved columns with actual G before declaring rank.
            actual = action(V[:, remaining], "rank_tail_recheck")
            tail = np.array(
                [
                    np.sqrt(squared_norm(V[:, k], actual[:, p]))
                    for p, k in enumerate(remaining)
                ]
            )
            GV[:, remaining] = actual
            if np.max(tail) <= QR_TOL:
                break
            # A different pivot can only follow this measured norm correction.
            if remaining[int(np.argmax(tail))] == j:
                raise ValueError("READOUT_QR_RANK_UNRESOLVED")
            continue
        q, gq = v / norm, gv / norm
        Q[:, rank], GQ[:, rank] = q, gq
        pivots.append(j)
        remaining.remove(j)
        for _ in range(2):
            if remaining:
                h = q.conj() @ GV[:, remaining]
                V[:, remaining] -= q[:, None] * h
                GV[:, remaining] -= gq[:, None] * h
        rank += 1
        if rank % 10 == 0 or not remaining:
            heartbeat("G_QR", dict(rank=rank, G_columns=action.count))
    if rank == 0:
        raise ValueError("READOUT_ZERO_NUMERICAL_SPAN")
    Q = Q[:, :rank].copy()
    permutation = np.asarray(pivots + sorted(remaining) + list(zero), dtype=int)
    R = Q.conj().T @ GU[:, permutation]
    action.check()
    left, singular, vh = np.linalg.svd(R, full_matrices=False)
    keep = singular > SVD_RCOND * singular[0]
    Qeff = Q @ left[:, keep]
    GQeff = action(Qeff, "effective_space_verification")
    Gd = action(d, "right_hand_side")
    d_ref = squared_norm(reference, action(reference, "reference_energy"))
    if d_ref <= 0:
        raise ValueError("READOUT_ZERO_REFERENCE")
    beta = Qeff.conj().T @ Gd
    z = vh[keep].conj().T @ (beta / singular[keep])
    delta_a = np.zeros(m, complex)
    nonzero_perm = scales[permutation] > 0
    delta_a[permutation[nonzero_perm]] = (
        z[nonzero_perm] / scales[permutation[nonzero_perm]]
    )
    delta_ideal = Qeff @ beta
    delta_columns = Phi @ delta_a
    residual = d - delta_ideal
    Gres = action(residual, "projection_residual_verification")
    QR_error = U[:, permutation] - Q @ R
    GQR_error = action(QR_error, "QR_reconstruction_verification")
    qr_energy = sum(squared_norm(QR_error[:, j], GQR_error[:, j]) for j in range(m))
    e0sq = squared_norm(d, Gd) / d_ref
    e1sq = squared_norm(residual, Gres) / d_ref
    removed = (
        squared_norm(delta_ideal, action(delta_ideal, "correction_energy")) / d_ref
    )
    orth = float(np.linalg.norm(Qeff.conj().T @ GQeff - np.eye(sum(keep))))
    optimal = float(np.linalg.norm(Qeff.conj().T @ Gres) / np.sqrt(d_ref))
    stats = dict(
        QR_threshold=QR_TOL,
        SVD_rcond=SVD_RCOND,
        QR_rank=rank,
        retained_rank=int(sum(keep)),
        singular_values=singular.tolist(),
        SVD_discarded_directions=np.flatnonzero(~keep).tolist(),
        zero_columns=zero.tolist(),
        QR_discarded_columns=sorted(remaining),
        permutation=permutation.tolist(),
        column_scales=scales.tolist(),
        G_orthogonality_F=orth,
        normalized_QR_G_F_relative=float(np.sqrt(qr_energy / len(nz))),
        retained_optimality=optimal,
        all_normalized_column_residual_correlations=(
            U.conj().T @ Gres / np.sqrt(d_ref)
        ).tolist(),
        E0_squared=e0sq,
        ideal_E1_squared=e1sq,
        correction_relative_energy=removed,
        nonincrease=e1sq <= e0sq + 1e-10,
        pythagorean_defect=abs(e0sq - e1sq - removed),
        gamma=removed / e0sq,
        delta_a_norm=float(np.linalg.norm(delta_a)),
        delta_a_max=float(np.max(np.abs(delta_a))),
    )
    return dict(
        Q=Q,
        Q_eff=Qeff,
        R=R,
        singular_values=singular,
        left=left,
        vh=vh,
        permutation=permutation,
        scales=scales,
        delta_a=delta_a,
        delta_ideal=delta_ideal,
        delta_columns=delta_columns,
    ), stats
