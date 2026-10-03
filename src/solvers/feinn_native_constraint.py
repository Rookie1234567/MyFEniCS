"""Opt-in saved-PDE8 native minimum subject to the original dual energy.

Only a bounded scalar constraint multiplier is varied. No FE action, inverse,
reference label, optimizer history, or production default enters this kernel.
"""

import numpy as np

from src.solvers.feinn_common_descent import (
    PDE_KEYS,
    finite,
    lower_certificate,
    objective,
    parameter_basis,
    quadratic,
    require,
    trust_ball,
)


def constrained_minimum(HN, aN, HR, aR):
    """Convex ball/conic problem, at most96 multiplier and80 ball root steps."""
    HN, aN, HR, aR = map(np.asarray, (HN, aN, HR, aR))
    n = len(aN)
    require(n > 0, "NO_RETAINED_PARAMETER_DIRECTIONS")
    require(HN.shape == HR.shape == (n, n) and aR.shape == (n,), "CONSTRAINT_LAYOUT")
    for value in (HN, aN, HR, aR):
        finite(value)
        require(np.isrealobj(value), "REAL_PARAMETER_QUADRATIC")
    for H in (HN, HR):
        tolerance = (
            256 * np.finfo(float).eps * max(np.linalg.norm(H, 2), np.finfo(float).tiny)
        )
        require(np.linalg.norm(H - H.T) <= tolerance, "NON_SYMMETRIC_QUADRATIC")
        require(
            np.linalg.eigvalsh(H)[0] >= -tolerance, "SUBSTANTIAL_NEGATIVE_CURVATURE"
        )
    best_u, upper, best_cert = np.zeros(n), 1.0, None
    trials = []

    def evaluate(lam):
        nonlocal best_u, upper, best_cert
        require(len(trials) < 96, "MULTIPLIER_EVALUATION_CAP")
        H, a = HN + lam * HR, aN + lam * aR
        u, info = trust_ball(H, a)
        N, R = objective(HN, aN, u), objective(HR, aR, u)
        cert = lower_certificate(H, a, lam, info["mu"])
        if (
            best_cert is None
            or cert["lower"] - cert["numerical_margin"]
            > best_cert["lower"] - best_cert["numerical_margin"]
        ):
            best_cert = cert
        if np.linalg.norm(u) <= 1 + 1e-12 and R <= 1 and N <= upper:
            best_u, upper = u.copy(), N
        trials.append(dict(lambda_=float(lam), N=N, R=R, **info))
        return R

    R = evaluate(0.0)
    if R > 1:
        lo, hi = 0.0, 1.0
        while len(trials) < 96:
            R = evaluate(hi)
            if R <= 1:
                break
            lo, hi = hi, hi * 2
        if R <= 1:
            while len(trials) < 96:
                if upper - best_cert["lower"] + best_cert["numerical_margin"] <= 1e-11:
                    break
                mid = (lo + hi) / 2
                if mid == lo or mid == hi:
                    break
                R = evaluate(mid)
                if R > 1:
                    lo = mid
                else:
                    hi = mid
    H = HN + best_cert["lambda_"] * HR
    a = aN + best_cert["lambda_"] * aR
    mu = best_cert["mu"]
    best_cert.update(
        stationarity=float(np.linalg.norm((H + mu * np.eye(n)) @ best_u + a)),
        ball_complementarity=float(abs(mu * (best_u @ best_u - 1))),
        residual_complementarity=float(
            abs(best_cert["lambda_"] * (objective(HR, aR, best_u) - 1))
        ),
    )
    width = upper - best_cert["lower"] + best_cert["numerical_margin"]
    return dict(
        u=best_u.tolist(),
        U=float(upper),
        certificate=best_cert,
        conservative_bound_width=float(width),
        multiplier_evaluations=len(trials),
        ball_root_iteration_max=max(row["root_iterations"] for row in trials),
        trials=trials,
        optimality="CERTIFIED_NARROW_BOUND" if width <= 1e-7 else "UNKNOWN",
    )


def native_candidate(packet, rcond):
    """Exact construction whitelist excludes fields, labels, and reference columns."""
    require(set(packet) == PDE_KEYS, "PDE_CONSTRUCTION_ALLOWLIST")
    theta_norm = float(packet["theta_norm"])
    require(np.isfinite(theta_norm) and theta_norm >= 0, "THETA_NORM")
    T, basis = parameter_basis(packet["P"], rcond)
    rho = 1e-3 * max(theta_norm, 1)
    Z = rho * packet["Y"] @ T
    WZ = rho * packet["WY"] @ T
    HN, aN, Nmeta = quadratic(Z, Z, packet["r"], packet["r"])
    HR, aR, Rmeta = quadratic(Z, WZ, packet["r"], packet["qr"])
    solution = constrained_minimum(HN, aN, HR, aR)
    u = np.asarray(solution["u"])
    return dict(
        data_role="REFERENCE_EXPOSED_DIAGNOSTIC",
        reference_used_for_construction=False,
        pde_only_solve=False,
        production_initialization_allowed=False,
        official_candidate_results=False,
        rho=rho,
        T=T.tolist(),
        basis=basis,
        alpha=(rho * T @ u).tolist(),
        delta_theta_norm=float(np.linalg.norm(packet["P"] @ (rho * T @ u))),
        quadratic_N=dict(H=HN.tolist(), a=aN.tolist(), **Nmeta),
        quadratic_R=dict(H=HR.tolist(), a=aR.tolist(), **Rmeta),
        solution=solution,
    )
