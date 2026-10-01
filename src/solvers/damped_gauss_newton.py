"""Real matrix-free damped Gauss–Newton with fixed CG/range-Ritz safeguards.

The caller supplies true objective/gradient and positive GN curvature actions.
This is not a nonlinear full Hessian and never builds a dense parameter K.
"""

from copy import deepcopy
from time import perf_counter
import numpy as np


def damped_cg(K, gradient, mu, *, preconditioner=None, max_iter=40, tolerance=0.01):
    rhs = -np.asarray(gradient, np.float64)
    s = np.zeros_like(rhs)
    norm = np.linalg.norm(rhs)
    if norm == 0:
        return s, dict(iterations=0, true_relative=0.0, converged=True, hit_limit=False)
    r = rhs.copy()
    P = preconditioner or (lambda v: v.copy())
    z = P(r)
    p = z.copy()
    rho = float(r @ z)
    if not rho > 0:
        raise ValueError("PC_NOT_POSITIVE")
    iterations = 0
    for iterations in range(1, max_iter + 1):
        Hp = K(p) + mu * p
        curvature = float(p @ Hp)
        if not np.isfinite(curvature) or curvature <= 0:
            raise ValueError("DAMPED_CURVATURE_NOT_POSITIVE")
        alpha = rho / curvature
        s += alpha * p
        r -= alpha * Hp
        if np.linalg.norm(r) <= tolerance * norm:
            true = rhs - K(s) - mu * s
            if np.linalg.norm(true) <= tolerance * norm:
                r = true
                break
            r = true
        z = P(r)
        rho_next = float(r @ z)
        if not np.isfinite(rho_next) or rho_next <= 0:
            if np.linalg.norm(r) <= tolerance * norm:
                break
            raise ValueError("CG_RESIDUAL_OR_PC_INVALID")
        p = z + (rho_next / rho) * p
        rho = rho_next
    true = rhs - K(s) - mu * s
    relative = float(np.linalg.norm(true) / norm)
    return s, dict(
        iterations=iterations,
        true_relative=relative,
        converged=relative <= tolerance,
        hit_limit=iterations >= max_iter,
        max_iter=max_iter,
        target_true_relative=tolerance,
        finite=bool(np.isfinite(s).all()),
    )


def range_ritz(K, size, *, rank=32, seed=421902, rcond=1e-12):
    started = perf_counter()
    rank = min(rank, size)
    omega = np.random.default_rng(seed).normal(size=(size, rank))
    Y = np.column_stack([K(omega[:, j]) for j in range(rank)])
    U, _ = np.linalg.qr(Y, mode="reduced")
    KU = np.column_stack([K(U[:, j]) for j in range(rank)])
    raw = U.T @ KU
    T = (raw + raw.T) / 2
    eigenvalues, W = np.linalg.eigh(T)
    scale = float(np.max(abs(eigenvalues), initial=0))
    negative_tolerance = 128 * np.finfo(float).eps * max(scale, np.finfo(float).tiny)
    if np.min(eigenvalues, initial=0) < -negative_tolerance:
        raise ValueError("RITZ_SIGNIFICANT_NEGATIVE_CURVATURE")
    eigenvalues = np.maximum(eigenvalues, 0)
    keep = eigenvalues > rcond * scale
    V = U @ W[:, keep]
    lam = eigenvalues[keep]
    return (
        V,
        lam,
        dict(
            rank_requested=rank,
            rank_retained=len(lam),
            seed=seed,
            rcond=rcond,
            K_actions=2 * rank,
            ritz_eigenvalues=eigenvalues.tolist(),
            negative_roundoff_tolerance=negative_tolerance,
            projected_symmetry_relative=float(
                np.linalg.norm(raw - raw.T) / max(np.linalg.norm(raw), 1e-30)
            ),
            orthogonality=float(np.linalg.norm(V.T @ V - np.eye(len(lam)))),
            basis_payload_bytes=V.nbytes,
            setup_seconds=perf_counter() - started,
        ),
    )


def apply_ritz_inverse(v, V, lam, mu):
    projected = V.T @ v
    return (v - V @ projected) / mu + V @ (projected / (lam + mu))


class DampedGNState:
    """Checkpointable optimizer state; no inherited Adam/L-BFGS history."""

    def __init__(self, h0, *, pc_max_builds=2):
        if not np.isfinite(h0) or h0 <= 0:
            raise ValueError("INITIAL_GN_SCALE_NOT_POSITIVE")
        self.h0 = float(h0)
        self.mu = 1e-3 * self.h0
        self.pc_max_builds = pc_max_builds
        self.accepted = 0
        self.slow_streak = 0
        self.pc_builds = []
        self.V = None
        self.lam = None
        self.last_pc_outer = -5

    def state_dict(self):
        return deepcopy(vars(self))

    def load_state_dict(self, state):
        self.__dict__.clear()
        self.__dict__.update(deepcopy(state))

    def clamp(self):
        self.mu = float(np.clip(self.mu, 1e-12 * self.h0, 1e6 * self.h0))

    def propose(self, theta, loss, gradient, K, evaluate, emit=lambda *_: None):
        """A rejected trial always leaves theta/forward state at committed theta."""
        theta = np.asarray(theta).copy()
        g = np.asarray(gradient)

        def trial(s, kind, cg=None):
            Ks = K(s)
            pred = float(-g @ s - 0.5 * s @ Ks)
            row = dict(
                kind=kind,
                mu=self.mu,
                gradient_norm=float(np.linalg.norm(g)),
                step_norm=float(np.linalg.norm(s)),
                g_dot_s=float(g @ s),
                pred=pred,
                cg=cg,
                PC_build_count=len(self.pc_builds),
                PC_source_outer=self.last_pc_outer if self.V is not None else None,
            )
            if (
                pred <= 0
                or not np.isfinite(pred)
                or g @ s >= 0
                or not np.isfinite(s).all()
            ):
                row.update(accepted=False, reason="NON_DESCENT_LOCAL_MODEL")
                emit(row)
                return False, None, row
            try:
                new = evaluate(theta + s)
            finally:
                # The caller's evaluate accepts restore_only without objective
                # work. Trial updates never mutate the committed optimizer.
                evaluate(theta, restore_only=True)
            ared = float(loss - new)
            eta = ared / pred
            accept = bool(np.isfinite(new) and ared > 0 and eta >= 0.1)
            row.update(
                ared=ared,
                eta=eta,
                trial_loss=float(new),
                accepted=accept,
                inexact_linear_solve=bool(cg is not None and not cg["converged"]),
            )
            emit(row)
            return accept, theta + s, row

        for damping_trial in range(8):
            pc = (
                (lambda v: apply_ritz_inverse(v, self.V, self.lam, self.mu))
                if self.V is not None
                else None
            )
            s, cg = damped_cg(
                K, g, self.mu, preconditioner=pc, max_iter=80 if pc is not None else 40
            )
            if cg["hit_limit"] and cg["true_relative"] > 0.01:
                self.slow_streak += 1
            else:
                self.slow_streak = 0
            if (
                self.slow_streak >= 3
                and len(self.pc_builds) < self.pc_max_builds
                and self.accepted - self.last_pc_outer >= 5
            ):
                V, lam, record = range_ritz(K, len(theta))
                record["source_accepted_outer"] = self.accepted
                self.pc_builds.append(record)
                self.last_pc_outer = self.accepted
                if len(lam):
                    self.V, self.lam = V, lam
                self.slow_streak = 0
                emit(dict(kind="PC_BUILD", **record))
            accepted, new, row = trial(s, "GN_TRIAL", cg)
            row["damping_trial"] = damping_trial
            if accepted:
                if row["eta"] > 0.75:
                    self.mu /= 3
                elif row["eta"] < 0.25:
                    self.mu *= 2
                self.clamp()
                self.accepted += 1
                return new, row
            self.mu *= 10
            self.clamp()
        Kg = K(g)
        curvature = float(g @ Kg)
        if curvature <= 0 or not np.isfinite(curvature):
            return None, dict(
                stop_reason="GN_MODEL_STAGNATION",
                gradient_norm=float(np.linalg.norm(g)),
                cauchy_curvature=curvature,
            )
        base = -(g @ g / curvature) * g
        for scale in (1.0, 0.5, 0.25):
            accepted, new, row = trial(scale * base, "CAUCHY_TRIAL")
            if accepted:
                self.accepted += 1
                return new, row
        return None, dict(
            stop_reason="GN_MODEL_STAGNATION",
            gradient_norm=float(np.linalg.norm(g)),
            cauchy_curvature=curvature,
        )
