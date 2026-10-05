"""Bounded exact reuse of the two-pass residual-space projection.

Q is the already accepted orthonormal residual basis, not a FE Gram matrix.
The small Q*Q product is never inverted or factored. In exact arithmetic,
(I-Q Q*)^2 b = b-Q (2 Q*b-(Q*Q) Q*b). Input sparsity can reduce Q*b; all
coordinates of the result remain present. Near cancellation retains the
original explicit two passes. The native operator and accepted QR are unchanged.
"""

from time import perf_counter

import numpy as np

from src.solvers.neural_wave_subspace import conjugate_product


class ResidualProjectionCache:
    def __init__(self, subspace, output_rows, *, additional_cache_bytes=0):
        start = perf_counter()
        self.space = subspace
        self.columns = subspace.m
        self.rows = np.unique(np.asarray(output_rows, dtype=np.int64))
        n = len(subspace.r)
        if np.any(self.rows < 0) or np.any(self.rows >= n):
            raise ValueError("RESIDUAL_PROJECTION_OUTPUT_SUPPORT_INVALID")
        self.mask = np.zeros(n, dtype=bool)
        self.mask[self.rows] = True
        plan = (self.columns**2 + len(self.rows) * self.columns) * 16 + n
        if plan + additional_cache_bytes > 2 * 2**30:
            raise MemoryError("DETACHED_PROJECTION_CACHE_2GIB_PLANNING_LINE")
        self.Q = subspace.Q[:, :self.columns]
        self.small_product = subspace.small_basis_inner_product()
        self.selected_Q = np.array(self.Q[self.rows], order="F", copy=True)
        self.counts = dict(project=0, explicit_two_pass_fallback=0)
        self.seconds = dict(build=perf_counter() - start, project=0.0)

    def project(self, values, *, supported=False):
        start = perf_counter()
        if self.space.m != self.columns:
            raise ValueError("RESIDUAL_PROJECTION_ACCEPTED_BASIS_CACHE_STALE")
        values = np.asarray(values)
        if values.shape[0] != len(self.mask) or values.ndim not in (1, 2):
            raise ValueError("RESIDUAL_PROJECTION_FULL_OUTPUT_LAYOUT_REQUIRED")
        if not np.isfinite(values).all():
            raise ValueError("RESIDUAL_PROJECTION_FINITE_VALUES_REQUIRED")
        if supported and np.any(values[~self.mask] != 0):
            raise ValueError("RESIDUAL_PROJECTION_EXACT_SUPPORT_FAILED")
        cross = conjugate_product(
            self.selected_Q if supported else self.Q,
            values[self.rows] if supported else values,
        )
        second = cross - self.small_product @ cross
        out = values - self.Q @ (cross + second)
        # This fixed rounding safeguard selects the original operation; it
        # changes no rank, loss, precision Gate or scientific stopping rule.
        if np.linalg.norm(out) <= 1e-6 * np.linalg.norm(values):
            out = self.space.project(values)
            self.counts["explicit_two_pass_fallback"] += 1
        self.counts["project"] += 1
        self.seconds["project"] += perf_counter() - start
        return out

    @property
    def retained_bytes(self):
        return self.selected_Q.nbytes + self.small_product.nbytes + self.rows.nbytes + self.mask.nbytes
