"""Bounded saved-array diagnostics. No FE actions, network or training imports.

The ball is in REAL PARAMETER space. Residual-only construction has an explicit
allowlist; reference fields enter only the later evaluator/oracle. Small PSD
trust problems provide primal points and reproducible Lagrangian lower bounds.
"""

import hashlib
import json
import os
from pathlib import Path

import numpy as np

EPS = np.finfo(np.float64).eps
PDE_KEYS = frozenset(("P", "Y", "WY", "r", "qr", "theta_norm"))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def finite(value):
    require(np.isfinite(value).all(), "NONFINITE_INPUT")


def atomic_json(path, value):
    """Exclusive final pathname; fsync before rename and directory fsync."""
    path = Path(path)
    require(not path.exists(), "IMMUTABLE_OUTPUT_EXISTS")
    payload = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return hashlib.sha256(payload).hexdigest()


def provenance_columns(descriptions, count, subset):
    require(subset in ("PDE8", "ALL16"), "DIRECTION_SET")
    active = [row for row in descriptions if "column" in row]
    require(sorted(row["column"] for row in active) == list(range(count)), "COLUMN_MAP")
    require(all(row["kind"] in ("PDE", "reference_G") for row in active), "COLUMN_KIND")
    require(len({(row["kind"], row["group"]) for row in active}) == count, "COLUMN_GROUP")
    return sorted(row["column"] for row in active if subset == "ALL16" or row["kind"] == "PDE")


def parameter_basis(P, rcond):
    P = np.asarray(P)
    require(P.dtype == np.float64 and P.ndim == 2 and P.shape[1] <= 16, "REAL_PARAMETER_LAYOUT")
    finite(P)
    require(rcond in (1e-10, 1e-12), "FIXED_RCOND")
    scales = np.linalg.norm(P, axis=0)
    safe = np.where(scales > 0, scales, 1)
    Z = P / safe
    # QR first confines the SVD to <=16 rows. At full rank, pulling its left
    # vectors back through R avoids cancellation in V/sigma for correlated P.
    _, R = np.linalg.qr(Z, mode="reduced")
    U, sigma, Vh = np.linalg.svd(R, full_matrices=False)
    keep = sigma > (rcond * sigma[0] if len(sigma) else 0)
    pullback = np.linalg.solve(R, U[:, keep]) if R.shape[0] == R.shape[1] and keep.all() else Vh[keep].T / sigma[keep]
    T = pullback / safe[:, None]
    Q = P @ T
    orth = np.linalg.norm(Q.T @ Q - np.eye(Q.shape[1]))
    reconstruction = np.linalg.norm(Z - Q @ (Q.T @ Z)) / max(np.linalg.norm(Z), 1)
    require(orth <= 1e-10, "PARAMETER_ORTHOGONALITY")
    return T, dict(rank=int(keep.sum()), rcond=rcond, singular_values=sigma.tolist(),
                   truncation=(~keep).tolist(), column_scales=scales.tolist(),
                   parameter_orthogonality=float(orth), parameter_reconstruction=float(reconstruction))


def quadratic(columns, weighted_columns, target, weighted_target):
    X, WX, x, wx = map(np.asarray, (columns, weighted_columns, target, weighted_target))
    require(X.ndim == 2 and WX.shape == X.shape and x.shape == wx.shape == (X.shape[0],), "PAIRED_LAYOUT")
    for value in (X, WX, x, wx):
        finite(value)
    d = np.vdot(x, wx)
    scale = np.linalg.norm(x) * np.linalg.norm(wx)
    require(d.real > 256 * EPS * scale and abs(d.imag) <= 256 * EPS * scale, "NONPOSITIVE_OR_NEAR_ZERO_DENOMINATOR")
    full = X.conj().T @ WX / d.real
    herm = np.linalg.norm(full - full.conj().T) / max(np.linalg.norm(full), np.finfo(float).tiny)
    require(herm <= 1e-10, "NONHERMITIAN_PAIRED_COLUMNS")
    H = (full.real + full.real.T) / 2
    a = (X.conj().T @ wx).real / d.real
    eigen = np.linalg.eigvalsh(H)
    tolerance = 256 * EPS * max(np.linalg.norm(H, 2) if len(a) else 0, np.finfo(float).tiny)
    require(not len(eigen) or eigen[0] >= -tolerance, "SUBSTANTIAL_NEGATIVE_CURVATURE")
    return H, a, dict(denominator=float(d.real), denominator_operation_scale=float(scale),
                      Hermitian_defect=float(herm), eigenvalues=eigen.tolist(), PSD_roundoff_allowance=float(tolerance))


def objective(H, a, u):
    return float(1 + 2 * a @ u + u @ H @ u)


def trust_ball(H, a):
    """PSD ball minimum, minimum norm when nonunique. <=80 scalar root steps.

    Only roundoff-size negative spectral values may be clipped for constructing
    a primal point. The lower certificate uses the ORIGINAL H plus mu I, and
    explicitly budgets the tiny extra multiplier used to make it positive.
    """
    H, a = np.asarray(H), np.asarray(a)
    finite(H)
    finite(a)
    require(H.shape == (len(a), len(a)), "SMALL_LAYOUT")
    if not len(a):
        return np.empty(0), dict(mu=0.0, root_iterations=0)
    d, V = np.linalg.eigh(H)
    allowance = 256 * EPS * max(np.linalg.norm(H, 2), np.finfo(float).tiny)
    require(d[0] >= -allowance, "SUBSTANTIAL_NEGATIVE_CURVATURE")
    b = V.T @ a
    positive = d > allowance
    u0 = np.zeros_like(a)
    u0[positive] = -b[positive] / d[positive]
    null_defect = np.linalg.norm(b[~positive])
    if np.linalg.norm(u0) <= 1 and null_defect <= 256 * EPS * max(np.linalg.norm(a), np.finfo(float).tiny):
        return V @ u0, dict(mu=0.0, root_iterations=0)
    dd = np.maximum(d, 0)
    lo, hi = 0.0, max(np.linalg.norm(a), np.linalg.norm(H, 2), np.finfo(float).tiny)
    steps = 0
    for steps in range(1, 81):
        mu = (lo + hi) / 2
        norm = np.linalg.norm(b / (dd + mu))
        if norm > 1:
            lo = mu
        else:
            hi = mu
        if hi - lo <= 16 * EPS * hi:
            break
    return -V @ (b / (dd + hi)), dict(mu=float(hi), root_iterations=steps)


def lower_certificate(H, a, weight, multiplier):
    """Lower bound and all defects; no inverse matrix is formed."""
    n = len(a)
    scale = max(np.linalg.norm(H, 2) if n else 0, np.linalg.norm(a), np.finfo(float).tiny)
    mu = max(multiplier, 0.0)
    # A tiny disclosed increase avoids an ambiguous singular spectral inverse.
    dmin = float(np.linalg.eigvalsh(H)[0]) if n else 0.0
    mu = max(mu, -dmin + 64 * EPS * scale) if n else 0.0
    M = H + mu * np.eye(n)
    spectrum, V = np.linalg.eigh(M)
    require(not n or spectrum[0] >= 0, "LOWER_BOUND_PSD")
    positive = spectrum > 0
    z = V[:, positive] @ ((V[:, positive].T @ a) / spectrum[positive]) if n else np.empty(0)
    require(np.linalg.norm(V[:, ~positive].T @ a) <= 1e-12 * max(np.linalg.norm(a), np.finfo(float).tiny), "LOWER_BOUND_RANGE")
    range_defect = np.linalg.norm(M @ z - a)
    L = float(1 - mu - a @ z)
    margin = float(4096 * EPS * (1 + abs(mu) + np.linalg.norm(H) + np.linalg.norm(a) * np.linalg.norm(z))
                   + 4 * range_defect * max(1, np.linalg.norm(z)))
    return dict(lambda_=float(weight), mu=float(mu), lower=L, numerical_margin=margin,
                spectrum=spectrum.tolist(), inverse_action=z.tolist(), range_defect=float(range_defect))


def common_minimum(HF, aF, HR, aR):
    """Concave dual bisection. Endpoints included in <=64 evaluations."""
    trials = []
    best_u, upper, best_cert = np.zeros_like(aF), 1.0, None

    def evaluate(weight):
        nonlocal best_u, upper, best_cert
        H, a = weight * HF + (1 - weight) * HR, weight * aF + (1 - weight) * aR
        u, info = trust_ball(H, a)
        F, R = objective(HF, aF, u), objective(HR, aR, u)
        if max(F, R) < upper:
            best_u, upper = u, max(F, R)
        cert = lower_certificate(H, a, weight, info["mu"])
        if best_cert is None or cert["lower"] - cert["numerical_margin"] > best_cert["lower"] - best_cert["numerical_margin"]:
            best_cert = cert
        trials.append(dict(lambda_=float(weight), F=F, R=R, **info))
        return u, F - R

    uR, left_derivative = evaluate(0.0)
    uF, right_derivative = evaluate(1.0)
    if left_derivative > 0 and right_derivative < 0:
        lo, hi = 0.0, 1.0
        for _ in range(62):
            weight = (lo + hi) / 2
            _, derivative = evaluate(weight)
            if upper - best_cert["lower"] + best_cert["numerical_margin"] <= 1e-10:
                break
            if derivative > 0:
                lo = weight
            else:
                hi = weight
    H = best_cert["lambda_"] * HF + (1 - best_cert["lambda_"]) * HR
    a = best_cert["lambda_"] * aF + (1 - best_cert["lambda_"]) * aR
    stationary = np.linalg.norm((H + best_cert["mu"] * np.eye(len(a))) @ best_u + a)
    best_cert.update(stationarity=float(stationary),
                     complementarity=float(abs(best_cert["mu"] * (best_u @ best_u - 1))))
    return dict(u=best_u.tolist(), u_R=uR.tolist(), u_F=uF.tolist(), U=float(upper),
                certificate=best_cert, gap=float(upper - best_cert["lower"]),
                endpoint_multipliers=dict(R=trials[0]["mu"], F=trials[1]["mu"]),
                lambda_evaluations=len(trials), root_iteration_max=max(x["root_iterations"] for x in trials))


def residual_candidate(packet, rcond):
    """This function CANNOT receive labels or reference-derived columns."""
    require(set(packet) == PDE_KEYS, "PDE_CONSTRUCTION_ALLOWLIST")
    theta_norm = float(packet["theta_norm"])
    require(np.isfinite(theta_norm) and theta_norm >= 0, "THETA_NORM")
    T, basis = parameter_basis(packet["P"], rcond)
    rho = 1e-3 * max(theta_norm, 1)
    H, a, q = quadratic(rho * packet["Y"] @ T, rho * packet["WY"] @ T, packet["r"], packet["qr"])
    u, info = trust_ball(H, a)
    return dict(data_role="UNLABELED_PDE8_RESIDUAL_CANDIDATE", reference_used_for_construction=False,
                rho=rho, T=T.tolist(), basis=basis, u=u.tolist(), alpha=(rho * T @ u).tolist(),
                residual_quadratic=q, H_R=H.tolist(), a_R=a.tolist(), trust=info)


def evaluate_step(raw, alpha, native_denominator):
    """Raw vector inner products; DERIVED_LOCAL_LINEAR_MODEL only."""
    alpha = np.asarray(alpha)
    row = {}
    for key, cols, wcols, target, wtarget in [("F", "X", "GX", "e", "Ge"), ("R", "Y", "WY", "r", "qr")]:
        d, wd = raw[cols] @ alpha, raw[wcols] @ alpha
        before = float(np.vdot(raw[target], raw[wtarget]).real)
        require(before > 0, "NONPOSITIVE_DENOMINATOR")
        cross = float(2 * np.vdot(raw[target], wd).real)
        update = float(np.vdot(d, wd).real)
        after = float(np.vdot(raw[target] + d, raw[wtarget] + wd).real)
        row[key] = after / before
        row[key + "_energy"] = dict(before=before, after=after, signed_cross=cross, update=update,
                                     reconstruction_defect=abs(after - before - cross - update) / max(before, abs(cross) + abs(update)))
    row.update(parameter_step_norm=float(np.linalg.norm(raw["P"] @ alpha)),
               native_linear=float(np.linalg.norm(raw["r"] + raw["Y"] @ alpha) / native_denominator),
               alpha=alpha.tolist(), value_kind="DERIVED_LOCAL_LINEAR_MODEL")
    return row


def classification(F, R, lower, margin, valid=True):
    if not valid:
        return "UNKNOWN"
    if max(F, R) <= 0.999 - 1e-10:
        return "COMMON_DESCENT_AT_LEAST_0P1_PERCENT"
    if lower - margin > 0.999 + 1e-10:
        return "NO_0P1_PERCENT_COMMON_DESCENT_IN_RETAINED_BALL"
    return "UNKNOWN_THRESHOLD_BRACKET"


def analyze_configuration(raw, theta_norm, rcond, native_denominator, candidate=None):
    """Oracle evaluation runs only AFTER the residual candidate is durable."""
    T, basis = parameter_basis(raw["P"], rcond)
    rho = 1e-3 * max(theta_norm, 1)
    HF, aF, Fmeta = quadratic(rho * raw["X"] @ T, rho * raw["GX"] @ T, raw["e"], raw["Ge"])
    HR, aR, Rmeta = quadratic(rho * raw["Y"] @ T, rho * raw["WY"] @ T, raw["r"], raw["qr"])
    common = common_minimum(HF, aF, HR, aR)
    points = {}
    for name, u in (("zero", np.zeros(T.shape[1])), ("residual", common["u_R"]),
                    ("field", common["u_F"]), ("common", common["u"])):
        u = np.asarray(u)
        alpha = rho * T @ u
        if name == "residual" and candidate is not None:
            require(np.allclose(alpha, candidate["alpha"], rtol=1e-10, atol=1e-13), "FROZEN_CANDIDATE_CHANGED")
            # Evaluate the exact previously hashed candidate, not an oracle substitute.
            alpha = np.asarray(candidate["alpha"])
        points[name] = dict(u=u.tolist(), **evaluate_step(raw, alpha, native_denominator))
    cert = common["certificate"]
    common_point = points["common"]
    valid = basis["parameter_reconstruction"] <= 1e-10 and max(
        p[k + "_energy"]["reconstruction_defect"] for p in points.values() for k in ("F", "R")) <= 1e-8
    return dict(rho=rho, rcond=rcond, T=T.tolist(), basis=basis, points=points, common=common,
                quadratic_F=dict(H=HF.tolist(), a=aF.tolist(), **Fmeta),
                quadratic_R=dict(H=HR.tolist(), a=aR.tolist(), **Rmeta),
                classification=classification(common_point["F"], common_point["R"], cert["lower"], cert["numerical_margin"], valid),
                bounds_closed=common["gap"] + cert["numerical_margin"] <= 1e-8,
                reference_used_for_oracle=True, true_NN_increment=False, pde_only_solve=False,
                official_candidate_results=False, production_initialization_allowed=False)
