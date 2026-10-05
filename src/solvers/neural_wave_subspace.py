"""Stable residual-space QR of learned FE columns, never a Maxwell inverse."""

from time import perf_counter

import numpy as np
from scipy import linalg


def conjugate_product(matrix, value):
    """BLAS conjugate transpose without allocating conjugate(full Q)."""
    if matrix.shape[1] == 0:
        return np.zeros((0,) + value.shape[1:], dtype=np.complex128)
    if value.ndim == 1:
        return linalg.blas.zgemv(1.0, matrix, value, trans=2)
    return linalg.blas.zgemm(1.0, matrix, value, trans_a=2)


class WaveSubspace:
    def __init__(self, action, capacity, *, rcond=1e-12):
        self.action, self.capacity, self.rcond = action, capacity, rcond
        n = action.size
        # U and Q only: AU is generated one column at a time, not retained.
        self.U = np.empty((n, capacity), dtype=np.complex128, order="F")
        self.Q = np.empty((n, capacity), dtype=np.complex128, order="F")
        self.R = np.zeros((capacity, capacity), dtype=np.complex128, order="F")
        self.m = 0
        self.c = np.zeros(n, dtype=np.complex128)
        self.r = action.f.copy()
        self.a = np.empty(0, dtype=np.complex128)
        self.seconds = dict(orthogonalize=0.0, solve=0.0, true_residual=0.0)

    def project(self, values):
        z = np.array(values, copy=True)
        if self.m:
            Q = self.Q[:, : self.m]
            # Two passes, including candidate blocks used by variable projection.
            for _ in range(2):
                z -= Q @ conjugate_product(Q, z)
        return z

    def add(self, column):
        if self.m >= self.capacity:
            raise ValueError("AUTHORIZED_COLUMN_CAPACITY_EXHAUSTED")
        start = perf_counter()
        u = np.asarray(column, dtype=np.complex128)
        w = self.action.apply(u)
        scale = float(np.linalg.norm(w))
        if not scale > 0:
            return dict(accepted=False, reason="ZERO_ACTION_COLUMN")
        u = u / scale
        z = w / scale
        cross = np.zeros(self.m, dtype=np.complex128)
        Q = self.Q[:, : self.m]
        for _ in range(2):
            h = conjugate_product(Q, z)
            cross += h
            z -= Q @ h
        independent = float(np.linalg.norm(z))
        self.seconds["orthogonalize"] += perf_counter() - start
        if independent <= self.rcond:
            return dict(accepted=False, reason="RANK_REJECTED", new_norm=independent)
        i = self.m
        self.U[:, i], self.Q[:, i] = u, z / independent
        self.R[:i, i], self.R[i, i] = cross, independent
        self.m += 1
        before = float(np.linalg.norm(self.r))
        previous = (self.a, self.c, self.r)
        start = perf_counter()
        rhs = conjugate_product(self.Q[:, : self.m], self.action.f)
        self.a = linalg.solve_triangular(self.R[: self.m, : self.m], rhs)
        self.c = self.U[:, : self.m] @ self.a
        self.seconds["solve"] += perf_counter() - start
        start = perf_counter()
        self.r = self.action.f - self.action.apply(self.c)
        after = float(np.linalg.norm(self.r))
        self.seconds["true_residual"] += perf_counter() - start
        small_svd_used = False
        if not np.isfinite(after) or after > before + 1e-10 * self.action.bnorm:
            # Fixed-threshold rank-revealing small solve, never a global inverse.
            small_svd_used = True
            self.a = linalg.lstsq(
                self.R[: self.m, : self.m], rhs, cond=self.rcond, lapack_driver="gelsd"
            )[0]
            self.c = self.U[:, : self.m] @ self.a
            self.r = self.action.f - self.action.apply(self.c)
            after = float(np.linalg.norm(self.r))
            if not np.isfinite(after) or after > before + 1e-10 * self.action.bnorm:
                self.m -= 1
                self.a, self.c, self.r = previous
                return dict(
                    accepted=False,
                    reason="SMALL_R_NUMERICAL_RANK_REJECTED",
                    trial_native_relative=after / self.action.bnorm,
                )
        return dict(
            accepted=True,
            index=i,
            scale=scale,
            new_norm=independent,
            native_relative=after / self.action.bnorm,
            actual_energy_decrease=before**2 - after**2,
            small_rank_revealing_svd_used=small_svd_used,
        )

    def rank_audit(self):
        """Small R only; no A^H A or full FE matrix is constructed."""
        if not self.m:
            return dict(rank=0, singular_values=[])
        singular = linalg.svdvals(self.R[: self.m, : self.m])
        rank = int(np.count_nonzero(singular > self.rcond * singular[0]))
        Q = self.Q[:, : self.m]
        orthogonal = np.linalg.norm(conjugate_product(Q, Q) - np.eye(self.m))
        normal = np.linalg.norm(conjugate_product(Q, self.r)) / self.action.bnorm
        return dict(
            rank=rank,
            columns=self.m,
            singular_values=singular.tolist(),
            rcond=self.rcond,
            orthogonality=float(orthogonal),
            projected_residual=float(normal),
        )


def optimal_amplitudes(action, subspace, columns, *, applied_columns=None):
    """Independent small SVD; both learned and fixed routes receive this."""
    B = (
        np.column_stack([action.apply(columns[:, j]) for j in range(columns.shape[1])])
        if applied_columns is None
        else np.asarray(applied_columns)
    )
    if B.shape != columns.shape or B.dtype != np.complex128 or not np.isfinite(B).all():
        raise ValueError("BOUNDED_ORIGINAL_ACTION_COLUMNS_INVALID")
    Z = subspace.project(B)
    left, singular, right = linalg.svd(Z, full_matrices=False)
    if not len(singular) or singular[0] == 0:
        raise ValueError("DEGENERATE_NEW_DIRECTION")
    keep = singular > subspace.rcond * singular[0]
    p = right[keep].conj().T @ ((left[:, keep].conj().T @ subspace.r) / singular[keep])
    z = Z @ p
    score = float(np.vdot(z, z).real)
    return (
        p,
        z,
        dict(score=score, rank=int(keep.sum()), singular_values=singular.tolist()),
    )
