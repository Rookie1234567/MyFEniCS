"""Real matrix-free damped Gauss–Newton with fixed CG/range-Ritz safeguards.

The caller supplies true objective/gradient and positive GN curvature actions.
This is not a nonlinear full Hessian and never builds a dense parameter K.
"""

from copy import deepcopy
from time import perf_counter
import numpy as np


def damped_cg(
    K,
    gradient,
    mu,
    *,
    preconditioner=None,
    max_iter=40,
    tolerance=0.01,
    budget=None,
    residual_to_original=None,
):
    rhs = -np.asarray(gradient, np.float64)
    s = np.zeros_like(rhs)
    norm = np.linalg.norm(rhs)
    original = residual_to_original or (lambda v: v)
    original_norm = np.linalg.norm(original(rhs))
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
    early = False
    for iterations in range(1, max_iter + 1):
        # Iteration action, optional convergence verification, final explicit
        # residual and proposal prediction can require four distinct K calls.
        if budget is not None and not budget.allow(K=4, trial=1):
            iterations -= 1
            early = True
            break
        Hp = K(p) + mu * p
        curvature = float(p @ Hp)
        if not np.isfinite(curvature) or curvature <= 0:
            raise ValueError("DAMPED_CURVATURE_NOT_POSITIVE")
        alpha = rho / curvature
        s += alpha * p
        r -= alpha * Hp
        if np.linalg.norm(r) <= tolerance * norm:
            true = rhs - K(s) - mu * s
            if (
                np.linalg.norm(true) <= tolerance * norm
                and np.linalg.norm(original(true)) <= tolerance * original_norm
            ):
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
    if budget is not None:
        budget.event("CG_TRUE_RESIDUAL", "begin", iterations=iterations)
    true = rhs - K(s) - mu * s
    if budget is not None:
        budget.event("CG_TRUE_RESIDUAL", "end", iterations=iterations)
    relative = float(np.linalg.norm(true) / norm)
    original_relative = float(np.linalg.norm(original(true)) / original_norm)
    return s, dict(
        iterations=iterations,
        true_relative=original_relative,
        transformed_true_relative=relative,
        original_parameter_true_relative=original_relative,
        converged=original_relative <= tolerance,
        hit_limit=iterations >= max_iter,
        max_iter=max_iter,
        target_true_relative=tolerance,
        finite=bool(np.isfinite(s).all()),
        budget_frontier_early=early,
    )


def range_ritz(K, size, *, rank=32, seed=421902, rcond=1e-12, budget=None):
    started = perf_counter()
    rank = min(rank, size)
    omega = np.random.default_rng(seed).normal(size=(size, rank))
    if budget is not None:
        budget.event("PC_K_OMEGA", "begin", rank=rank)
    Y = np.column_stack([K(omega[:, j]) for j in range(rank)])
    if budget is not None:
        budget.event("PC_K_OMEGA", "end", rank=rank)
    U, _ = np.linalg.qr(Y, mode="reduced")
    if budget is not None:
        budget.event("PC_KU", "begin", rank=rank)
    KU = np.column_stack([K(U[:, j]) for j in range(rank)])
    if budget is not None:
        budget.event("PC_KU", "end", rank=rank)
    raw = U.T @ KU
    T = (raw + raw.T) / 2
    if budget is not None:
        budget.event("PC_EIGH", "begin", rank=rank)
    eigenvalues, W = np.linalg.eigh(T)
    if budget is not None:
        budget.event("PC_EIGH", "end", rank=rank)
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

    def propose(
        self,
        theta,
        loss,
        gradient,
        K,
        evaluate,
        emit=lambda *_: None,
        *,
        budget=None,
        parameter_metric=None,
    ):
        """A rejected trial always leaves theta/forward state at committed theta."""
        theta = np.asarray(theta).copy()
        g = np.asarray(gradient)

        def trial(s, kind, cg=None, damping_trial=None):
            if budget is not None and not budget.allow(K=1, trial=1):
                raise budget.stop_exception("BUDGET_FRONTIER_TRIAL_RESERVE")
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
                damping_trial=damping_trial,
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
                if budget is not None:
                    budget.event("TRUE_TRIAL", "begin", trial_kind=kind)
                new = evaluate(theta + s)
            finally:
                # The caller's evaluate accepts restore_only without objective
                # work. Trial updates never mutate the committed optimizer.
                evaluate(theta, restore_only=True)
                if budget is not None:
                    budget.event("TRUE_TRIAL", "end", trial_kind=kind)
            finite = bool(np.isfinite(new))
            ared = float(loss - new) if finite else None
            eta = ared / pred if finite else None
            accept = bool(finite and ared > 0 and eta >= 0.1)
            row.update(
                ared=ared,
                eta=eta,
                trial_loss=float(new) if finite else None,
                accepted=accept,
                reason="TRUE_OBJECTIVE_ACCEPTANCE"
                if finite
                else "NONFINITE_TRIAL_REJECTED",
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
            if budget is not None:
                if not budget.allow(K=4, trial=1):
                    raise budget.stop_exception("BUDGET_FRONTIER_CG_RESERVE")
                budget.event("CG", "begin", damping_trial=damping_trial)
            if parameter_metric is not None and pc is not None:
                raise ValueError("PARAMETER_METRIC_PILOT_FORBIDS_PC")
            s, cg = (
                parameter_metric.solve if parameter_metric is not None else damped_cg
            )(
                K,
                g,
                self.mu,
                preconditioner=pc,
                max_iter=80 if pc is not None else 40,
                budget=budget,
            )
            if budget is not None:
                budget.event("CG", "end", damping_trial=damping_trial, **cg)
            if cg["hit_limit"] and cg["true_relative"] > 0.01:
                self.slow_streak += 1
            else:
                self.slow_streak = 0
            if (
                self.slow_streak >= 3
                and len(self.pc_builds) < self.pc_max_builds
                and self.accepted - self.last_pc_outer >= 5
            ):
                if budget is not None and not budget.allow(K=67, trial=1):
                    emit(
                        dict(
                            kind="PC_DEFERRED_BY_BUDGET",
                            retained_PC_builds=len(self.pc_builds),
                            accepted_outer=self.accepted,
                        )
                    )
                else:
                    if budget is not None:
                        budget.event("PC_BUILD", "begin", source_outer=self.accepted)
                    V, lam, record = range_ritz(K, len(theta), budget=budget)
                    record["source_accepted_outer"] = self.accepted
                    self.pc_builds.append(record)
                    self.last_pc_outer = self.accepted
                    if len(lam):
                        self.V, self.lam = V, lam
                    self.slow_streak = 0
                    emit(dict(kind="PC_BUILD", **record))
                    if budget is not None:
                        budget.event("PC_BUILD", "end", source_outer=self.accepted)
            accepted, new, row = trial(s, "GN_TRIAL", cg, damping_trial)
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
        d = g if parameter_metric is None else parameter_metric.inverse * g
        Kg = K(d)
        curvature = float(d @ Kg)
        if curvature <= 0 or not np.isfinite(curvature):
            return None, dict(
                stop_reason="GN_MODEL_STAGNATION",
                gradient_norm=float(np.linalg.norm(g)),
                cauchy_curvature=curvature,
            )
        base = -(g @ d / curvature) * d
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
