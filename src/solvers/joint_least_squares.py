"""Real matrix-free augmented least squares and bounded GN trial decisions.

The existing GN state supplies initialization and transactional serialization.
This opt-in controller uses explicit LSMR damping, without Gram/range-Ritz PC.
"""

import numpy as np
from scipy.sparse.linalg import LinearOperator, lsmr
from src.solvers.damped_gauss_newton import DampedGNState


def realify(z):
    z = np.asarray(z, dtype=np.complex128).reshape(-1)
    return np.concatenate((z.real, z.imag))


def complexify(v):
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    if len(v) % 2:
        raise ValueError("REALIFIED_COMPLEX_LAYOUT")
    n = len(v) // 2
    return v[:n] + 1j * v[n:]


def augmented_operator(J, damping):
    if not np.isfinite(damping) or damping <= 0:
        raise ValueError("POSITIVE_EXPLICIT_LS_DAMPING_REQUIRED")
    m, n = J.shape
    root = np.sqrt(damping)
    return LinearOperator(
        (m + n, n),
        matvec=lambda v: np.concatenate((J.matvec(v), root * v)),
        rmatvec=lambda u: J.rmatvec(u[:m]) + root * u[m:],
        dtype=np.float64,
    )


def solve_augmented(J, e, damping, *, maxiter=200):
    """Report true augmented residual and normal defect, not solver flags."""
    if not 1 <= maxiter <= 200:
        raise ValueError("JOINT_LSMR_FIXED_MAXIMUM_200")
    aug = augmented_operator(J, damping)
    rhs = np.concatenate((-np.asarray(e), np.zeros(J.shape[1])))
    solved = lsmr(
        aug,
        rhs,
        atol=1e-6,
        btol=1e-6,
        conlim=1e12,
        maxiter=maxiter,
        x0=np.zeros(J.shape[1]),
    )
    v = solved[0]
    jv = J.matvec(v)
    residual = np.concatenate((jv + e, np.sqrt(damping) * v))
    normal = aug.rmatvec(residual)
    initial = aug.rmatvec(rhs)
    return (
        v,
        jv,
        dict(
            iterations=int(solved[2]),
            stop_code=int(solved[1]),
            maxiter=maxiter,
            atol=1e-6,
            btol=1e-6,
            conlim=1e12,
            explicit_damping=damping,
            scipy_damp_argument=0,
            true_augmented_residual_norm=float(np.linalg.norm(residual)),
            augmented_rhs_norm=float(np.linalg.norm(rhs)),
            true_normal_defect_norm=float(np.linalg.norm(normal)),
            initial_normal_rhs_norm=float(np.linalg.norm(initial)),
            true_normal_defect_relative=float(
                np.linalg.norm(normal) / max(np.linalg.norm(initial), 1e-30)
            ),
            reported_normr=float(solved[3]),
            reported_normar=float(solved[4]),
            reported_normA=float(solved[5]),
            reported_condA=float(solved[6]),
            inexact_at_iteration_limit=bool(solved[2] == maxiter and solved[1] == 7),
            original_PDE_pass_from_stop_code=False,
        ),
    )


def prediction(e, jv):
    return float((np.dot(e, e) - np.dot(e + jv, e + jv)) / 2)


def cauchy_step(J, e, damping):
    q = J.rmatvec(e)
    jq = J.matvec(q)
    qq = float(q @ q)
    denominator = float(jq @ jq + damping * qq)
    if not qq > 0 or not denominator > 0:
        return None, None
    alpha = qq / denominator
    return -alpha * q, -alpha * jq


class JointLMState(DampedGNState):
    """Review-specific opt-in decisions; never invokes inherited PC/CG paths."""

    def __init__(self, h):
        super().__init__(h, pc_max_builds=0)
        self.trials = 0
        self.rejected = 0
        self.rejection_streak = 0
        self.lsmr_iterations = 0
        self.lost_iterations_upper_bound = 0
        self.pending_inner = None
        self.pending_trial = False
        self.lost_trial_upper_bound = 0

    def clamp(self):
        self.mu = float(np.clip(self.mu, 1e-12 * self.h0, 1e8 * self.h0))

    def decide(self, old_loss, trial_loss, pred):
        finite = np.isfinite(trial_loss) and np.isfinite(pred)
        ared = float(old_loss - trial_loss) if np.isfinite(trial_loss) else None
        rho = ared / pred if finite and pred > 0 else None
        accepted = bool(finite and pred > 0 and ared > 0 and rho >= 0.1)
        old_mu = self.mu
        self.trials += 1
        if accepted:
            self.accepted += 1
            self.rejection_streak = 0
            if rho > 0.75:
                self.mu /= 3
            elif rho < 0.25:
                self.mu *= 2
        else:
            self.rejected += 1
            self.rejection_streak += 1
            self.mu *= 10
        self.clamp()
        return dict(
            pred=float(pred) if np.isfinite(pred) else None,
            ared=ared,
            rho=rho,
            accepted=accepted,
            old_training_loss=float(old_loss),
            trial_training_loss=float(trial_loss) if np.isfinite(trial_loss) else None,
            damping_before=old_mu,
            damping_after=self.mu,
            consecutive_rejections=self.rejection_streak,
        )

    def recover_lost_inner(self):
        if self.pending_trial:
            self.trials += 1
            self.lost_trial_upper_bound += 1
            self.pending_trial = False
        if self.pending_inner is not None:
            charged = int(self.pending_inner)
            self.lsmr_iterations += charged
            self.lost_iterations_upper_bound += charged
            self.pending_inner = None
            return charged
        return 0


def power_scale(J, *, seed=4214701, iterations=4):
    rng = np.random.default_rng(seed)
    v = rng.choice([-1.0, 1.0], size=J.shape[1])
    v /= np.linalg.norm(v)
    rays = []
    for _ in range(iterations):
        jv = J.matvec(v)
        rays.append(float(jv @ jv))
        q = J.rmatvec(jv)
        norm = np.linalg.norm(q)
        if not norm > 0:
            return 0.0, dict(
                seed=seed,
                iterations=len(rays),
                rayleigh=rays,
                exact_spectral_bound=False,
                zero_action_requires_independent_witness=True,
            )
        v = q / norm
    return rays[-1], dict(
        seed=seed, iterations=iterations, rayleigh=rays, exact_spectral_bound=False
    )
