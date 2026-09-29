"""Bounded complex non-Hermitian Schur minimum-residual two-level research PC.

Only tall, rank-limited bases and a small triangular factor are owned here.
The original operator and unchanged geometric local PC are borrowed.
"""

import time

import numpy as np
from scipy.linalg import blas, qr, svd, svdvals

from .coarse_inverse_protocol import FactorDeclaration

RANK_THRESHOLD = 1.0e-10
RANK_MAX = 128
CAP = 512 * 2**20


def space_budget(rows, rank, local_representation=0, local_factor_bytes=0):
    if not 0 < rank <= RANK_MAX or rank >= rows:
        raise ValueError("bounded nonempty coarse space required")
    tall = rows * rank * 16
    small = rank * rank * 16
    # Include both FGMRES32 vector families, PC/S scratch and original audits.
    online = 2 * tall + (80 * rows + 8 * rank) * 16 + local_representation
    # Input, SVD/QR input copies, outputs, one deterministic rotation, LAPACK
    # work reserves; lifecycle is sequential, not all stages simultaneously.
    construction = 10 * tall + 12 * small + online - 2 * tall
    if construction > CAP or local_factor_bytes + small > CAP:
        raise ValueError("preconstruction representation/factor capacity exceeded")
    return {
        "rows": rows,
        "rank_cap": rank,
        "one_tall_array_bytes": tall,
        "online_representation_bound_bytes": online,
        "construction_representation_workspace_bound_bytes": construction,
        "small_R_factor_bound_bytes": small,
        "all_factor_bound_bytes": local_factor_bytes + small,
        "representation_cap_bytes": CAP,
        "factor_cap_bytes": CAP,
        "conjugate_transpose_copy": False,
        "lapack_workspace_policy": "conservative ten tall / twelve small array envelopes",
    }


def effective_rank(singular_values):
    values = np.asarray(singular_values)
    return (
        int(np.count_nonzero(values > RANK_THRESHOLD * values[0]))
        if len(values) and values[0]
        else 0
    )


def error_space(weighted_snapshots):
    """Unit-error/family-weighted snapshots; never residual POD or rank filling."""
    if weighted_snapshots.ndim != 2 or not np.isfinite(weighted_snapshots).all():
        raise ValueError("finite error snapshot matrix required")
    space_budget(*weighted_snapshots.shape)
    u, values, _ = svd(
        weighted_snapshots,
        full_matrices=False,
        lapack_driver="gesdd",
        check_finite=False,
    )
    rank = effective_rank(values)
    if not rank:
        raise ValueError("COARSE_SPACE_NUMERICAL_BLOCKED: no error directions")
    return np.array(u[:, :rank], dtype=np.complex128, order="F"), values


def build_schur_encoding(z, operator):
    """One fixed-threshold dependency rotation, followed by a fresh thin QR."""
    z = np.array(z, dtype=np.complex128, order="F", copy=True)
    space_budget(*z.shape)
    image = np.empty_like(z, order="F")
    for j in range(z.shape[1]):
        image[:, j] = operator(z[:, j])
    u, r = qr(image, mode="economic", check_finite=False)
    spectrum = svdvals(r, check_finite=False)
    before = z.shape[1]
    rank = effective_rank(spectrum)
    rotation = False
    if rank == 0:
        raise ValueError(
            "COARSE_SPACE_NUMERICAL_BLOCKED: SZ has no effective directions"
        )
    if rank != before:
        _, _, vh = svd(r, full_matrices=False, check_finite=False)
        z = np.asfortranarray(z @ vh[:rank].conj().T)
        del image, u, r, vh
        image = np.empty_like(z, order="F")
        for j in range(rank):
            image[:, j] = operator(z[:, j])
        u, r = qr(image, mode="economic", check_finite=False)
        spectrum_after = svdvals(r, check_finite=False)
        rotation = True
        if effective_rank(spectrum_after) != rank:
            raise ValueError(
                "COARSE_SPACE_NUMERICAL_BLOCKED: one dependency removal insufficient"
            )
    else:
        spectrum_after = spectrum
    reconstruction = np.linalg.norm(image - u @ r) / max(
        np.linalg.norm(image), np.finfo(float).tiny
    )
    orthogonality = np.linalg.norm(u.conj().T @ u - np.eye(rank)) / max(
        1.0, np.sqrt(rank)
    )
    if not np.isfinite(r).all() or max(reconstruction, orthogonality) > 1.0e-10:
        raise ValueError("COARSE_SPACE_NUMERICAL_BLOCKED: Schur QR identity")
    return (
        z,
        np.asfortranarray(u),
        np.asfortranarray(r),
        {
            "input_rank": before,
            "effective_rank": rank,
            "rank_relative_threshold": RANK_THRESHOLD,
            "dependency_rotation_once": rotation,
            "singular_values_before": spectrum.tolist(),
            "singular_values_after": spectrum_after.tolist(),
            "R_condition_2": float(spectrum_after[0] / spectrum_after[-1]),
            "QR_reconstruction_relative": float(reconstruction),
            "U_orthogonality_relative": float(orthogonality),
            "Z_orthogonality_relative": float(
                np.linalg.norm(z.conj().T @ z - np.eye(rank)) / max(1.0, np.sqrt(rank))
            ),
            "SZ_columns_orthogonality": "not assumed; U is orthonormal Schur image basis",
            "regularization_shift_pseudoinverse": False,
        },
    )


class BalancedTwoLevelPC:
    def __init__(self, local, operator, z, u, r):
        n, rank = z.shape
        if z.dtype != np.complex128 or u.shape != (n, rank) or r.shape != (rank, rank):
            raise ValueError("canonical complex Schur encoding shape required")
        if any(
            a.dtype != np.complex128
            or not a.flags.f_contiguous
            or not np.isfinite(a).all()
            for a in (z, u, r)
        ):
            raise ValueError(
                "finite Fortran complex128 encoding required without hidden copies"
            )
        if effective_rank(svdvals(r, check_finite=False)) != rank:
            raise ValueError("COARSE_SPACE_NUMERICAL_BLOCKED: rank-deficient R")
        if np.any(np.tril(r, -1)):
            raise ValueError("R must be triangular")
        self.budget = space_budget(
            n, rank, local.representation_bytes, local.factor_bytes
        )
        self.local, self.operator, self.z, self.u, self.r = local, operator, z, u, r
        for a in (z, u, r):
            a.flags.writeable = False
        self.rows, self.rank = n, rank
        self.coefficients = np.empty(rank, dtype=np.complex128)
        self.projected = np.empty(rank, dtype=np.complex128)
        self.rp, self.zc, self.tail, self.output = (
            np.empty(n, dtype=np.complex128) for _ in range(4)
        )
        self.calls = self.coarse_calls = self.local_calls = self.operator_calls = 0
        self.seconds = self.coarse_seconds = self.local_seconds = (
            self.operator_seconds
        ) = 0.0
        self.representation_bytes = (
            local.representation_bytes + z.nbytes + u.nbytes + (80 * n + 8 * rank) * 16
        )

    def project(self, source):
        return self._project(source).copy()

    def _project(self, source):
        return blas.zgemv(1.0, self.u, source, trans=2, y=self.projected, overwrite_y=1)

    def coarse_array(self, source):
        result = np.empty(self.rows, dtype=np.complex128)
        self._coarse(source, result)
        return result

    def _decode(self, coefficients, target):
        self.coefficients[:] = coefficients
        solved = blas.ztrsv(self.r, self.coefficients, overwrite_x=1)
        if not np.isfinite(solved).all():
            raise ValueError(
                "COARSE_SPACE_NUMERICAL_BLOCKED: triangular solve nonfinite"
            )
        blas.zgemv(1.0, self.z, solved, y=target, overwrite_y=1)

    def _coarse(self, source, target):
        started = time.perf_counter()
        self._decode(self._project(source), target)
        self.coarse_calls += 1
        self.coarse_seconds += time.perf_counter() - started

    def apply_array(self, source):
        source = np.asarray(source)
        if (
            source.shape != (self.rows,)
            or source.dtype != np.complex128
            or not np.isfinite(source).all()
        ):
            raise ValueError("complete finite complex residual required")
        started = time.perf_counter()
        coarse_started = time.perf_counter()
        a = self._project(source)
        self._decode(a, self.zc)
        self.rp[:] = source
        blas.zgemv(-1.0, self.u, a, beta=1.0, y=self.rp, overwrite_y=1)
        self.coarse_calls += 1
        self.coarse_seconds += time.perf_counter() - coarse_started
        local_started = time.perf_counter()
        y = self.local.apply_array(self.rp)
        self.local_calls += 1
        self.local_seconds += time.perf_counter() - local_started
        operator_started = time.perf_counter()
        image = self.operator(y)
        self.operator_calls += 1
        self.operator_seconds += time.perf_counter() - operator_started
        self._coarse(image, self.tail)
        np.add(self.zc, y, out=self.output)
        self.output -= self.tail
        if not np.isfinite(self.output).all():
            raise ValueError("two-level action nonfinite")
        result = self.output.copy()
        self.calls += 1
        self.seconds += time.perf_counter() - started
        return result

    def apply(self, _pc, source, target):
        target.array[:] = self.apply_array(source.getArray(readonly=True))

    @property
    def declarations(self):
        return self.local.declarations + (
            FactorDeclaration("bottom", self.rank, self.r.nbytes),
        )

    def counters(self):
        return {
            "B2_calls": self.calls,
            "C_calls": self.coarse_calls,
            "B_calls": self.local_calls,
            "S_calls_in_B2": self.operator_calls,
            "B2_seconds_inclusive": self.seconds,
            "C_seconds_child": self.coarse_seconds,
            "B_seconds_child": self.local_seconds,
            "S_seconds_child": self.operator_seconds,
            "nested_timers_not_additive": True,
        }


def algebra_audit(pc, *, seed=420701, count=3):
    """A few true actions; operation-scaled defects, not convergence evidence."""
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(count):
        a = rng.standard_normal(pc.rank) + 1j * rng.standard_normal(pc.rank)
        a /= np.linalg.norm(a)
        z = pc.z @ a
        sz = pc.operator(z)
        csz = pc.coarse_array(sz)
        bsz = pc.apply_array(sz)
        r = rng.standard_normal(pc.rows) + 1j * rng.standard_normal(pc.rows)
        r /= np.linalg.norm(r)
        cr = pc.coarse_array(r)
        scr = pc.operator(cr)
        b2r = pc.apply_array(r)
        sb2r = pc.operator(b2r)
        projection = pc.u @ pc.project(r)
        tiny = np.finfo(float).tiny
        row = {
            "CSZ_relative": float(
                np.linalg.norm(csz - z)
                / max(np.linalg.norm(csz) + np.linalg.norm(z), tiny)
            ),
            "SC_vs_UUH_operation_relative": float(
                np.linalg.norm(scr - projection)
                / max(np.linalg.norm(scr) + np.linalg.norm(projection), tiny)
            ),
            "B2SZ_operation_relative": float(
                np.linalg.norm(bsz - z)
                / max(np.linalg.norm(bsz) + np.linalg.norm(z), tiny)
            ),
            "UH_remaining_operation_relative": float(
                np.linalg.norm(pc.project(r - sb2r))
                / max(np.linalg.norm(r) + np.linalg.norm(sb2r), tiny)
            ),
        }
        rows.append(row)
    passed = all(np.isfinite(v) and v <= 1.0e-10 for row in rows for v in row.values())
    return {
        "passed": passed,
        "limit": 1.0e-10,
        "directions": rows,
        "seed": seed,
        "counters_including_audit": pc.counters(),
    }
