"""Independent saved-vector/KKT verifier; no producer or optimizer imports."""

import numpy as np

EPS = np.finfo(float).eps


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def same(actual, expected, scale=1.0):
    actual, expected = np.asarray(actual), np.asarray(expected)
    require(
        np.isfinite(actual).all() and np.isfinite(expected).all(), "NONFINITE_RECORD"
    )
    require(actual.shape == expected.shape, "RECORD_LAYOUT")
    require(
        np.linalg.norm(actual - expected)
        <= 1e-10 * max(float(scale), np.linalg.norm(expected), np.finfo(float).tiny),
        "RAW_RECORD_MISMATCH",
    )


def direct_points(raw, alpha, denominator):
    """Original complex array inner products, no weighted proxy or solver."""
    alpha = np.asarray(alpha, float)
    out = dict(
        alpha=alpha.tolist(),
        parameter_step_norm=float(np.linalg.norm(raw["P"] @ alpha)),
    )
    for name, target, wt, columns, wc in (
        ("N", "r", "r", "Y", "Y"),
        ("R", "r", "qr", "Y", "WY"),
        ("F", "e", "Ge", "X", "GX"),
    ):
        t, w = raw[target], raw[wt]
        d, wd = raw[columns] @ alpha, raw[wc] @ alpha
        original = np.vdot(t, w)
        require(
            original.real > 256 * EPS * np.linalg.norm(t) * np.linalg.norm(w),
            "INVALID_ENERGY_DENOMINATOR",
        )
        require(
            abs(original.imag) <= 256 * EPS * np.linalg.norm(t) * np.linalg.norm(w),
            "NONREAL_ENERGY_DENOMINATOR",
        )
        before = float(original.real)
        cross, square = float(2 * np.vdot(t, wd).real), float(np.vdot(d, wd).real)
        after = float(np.vdot(t + d, w + wd).real)
        scale = max(before, after, abs(cross) + abs(square))
        require(
            abs(after - before - cross - square) <= 1e-10 * scale, "RAW_CROSS_CLOSURE"
        )
        out[name] = after / before
        out[name + "_energy"] = dict(
            before=before,
            after=after,
            signed_cross=cross,
            update=square,
            closure_defect=abs(after - before - cross - square) / scale,
        )
    out["native"] = float(np.linalg.norm(raw["r"] + raw["Y"] @ alpha) / denominator)
    return out


def verify(candidate, raw, points, old_alpha, denominator):
    require(
        candidate["reference_used_for_construction"] is False, "CANDIDATE_LABEL_POLICY"
    )
    require(
        candidate["data_role"] == "REFERENCE_EXPOSED_DIAGNOSTIC", "CANDIDATE_USE_POLICY"
    )
    require(
        candidate["pde_only_solve"] is False
        and candidate["official_candidate_results"] is False
        and candidate["production_initialization_allowed"] is False,
        "CANDIDATE_USE_POLICY",
    )
    for value in raw.values():
        require(np.isfinite(value).all(), "NONFINITE_RAW_INPUT")
    T, rho = np.asarray(candidate["T"]), candidate["rho"]
    u, alpha = np.asarray(candidate["solution"]["u"]), np.asarray(candidate["alpha"])
    require(T.shape == (raw["P"].shape[1], len(u)), "CANDIDATE_PARAMETER_LAYOUT")
    Q = raw["P"] @ T
    orth = np.linalg.norm(Q.T @ Q - np.eye(len(u)))
    require(orth <= 1e-10, "PARAMETER_ORTHOGONALITY")
    same(alpha, rho * T @ u)
    Z, WZ = rho * raw["Y"] @ T, rho * raw["WY"] @ T
    Hs, aas = {}, {}
    for label, weights, wtarget in (("N", Z, raw["r"]), ("R", WZ, raw["qr"])):
        denom = float(np.vdot(raw["r"], wtarget).real)
        full = Z.conj().T @ weights / denom
        Hs[label] = (full.real + full.real.T) / 2
        aas[label] = (Z.conj().T @ wtarget).real / denom
        same(candidate["quadratic_" + label]["H"], Hs[label])
        same(candidate["quadratic_" + label]["a"], aas[label])
        same(candidate["quadratic_" + label]["denominator"], denom)
        allowance = 256 * EPS * max(np.linalg.norm(Hs[label], 2), np.finfo(float).tiny)
        require(np.linalg.eigvalsh(Hs[label])[0] >= -allowance, "NON_PSD_INPUT")
    values = {}
    for name, a in (
        ("zero", np.zeros_like(alpha)),
        ("original_R_minimum", old_alpha),
        ("native_constrained", alpha),
    ):
        values[name] = direct_points(raw, a, denominator)
        require(set(points[name]) == set(values[name]), "POINT_FIELDS_CHANGED")
        for field, value in values[name].items():
            if isinstance(value, dict):
                for key, number in value.items():
                    same(points[name][field][key], number)
            else:
                same(points[name][field], value)
    row = values["native_constrained"]
    for label in ("N", "R"):
        same(row[label], 1 + 2 * aas[label] @ u + u @ Hs[label] @ u)
    cert = candidate["solution"]["certificate"]
    lam, mu = float(cert["lambda_"]), float(cert["mu"])
    require(np.isfinite([lam, mu]).all() and lam >= 0 and mu >= 0, "INVALID_MULTIPLIER")
    H = Hs["N"] + lam * Hs["R"]
    a = aas["N"] + lam * aas["R"]
    B = H + mu * np.eye(len(u))
    d, V = np.linalg.eigh(B)
    require(d[0] >= 0, "INVALID_LOWER_BOUND_PSD")
    keep = d > 0
    require(
        np.linalg.norm(V[:, ~keep].T @ a)
        <= 1e-12 * max(np.linalg.norm(a), np.finfo(float).tiny),
        "INVALID_LOWER_BOUND_RANGE",
    )
    z = V[:, keep] @ ((V[:, keep].T @ a) / d[keep])
    lower = float(1 - mu - a @ z)
    defect = float(np.linalg.norm(B @ z - a))
    margin = float(
        4096
        * EPS
        * (1 + abs(mu) + np.linalg.norm(H) + np.linalg.norm(a) * np.linalg.norm(z))
        + 4 * defect * max(1, np.linalg.norm(z))
    )
    same(cert["lower"], lower)
    same(cert["inverse_action"], z)
    same(cert["numerical_margin"], margin)
    same(cert["stationarity"], np.linalg.norm(B @ u + a))
    same(cert["ball_complementarity"], abs(mu * (u @ u - 1)))
    same(cert["residual_complementarity"], abs(lam * (row["R"] - 1)))
    upper = row["N"]
    same(candidate["solution"]["U"], upper)
    width = upper - lower + margin
    same(candidate["solution"]["conservative_bound_width"], width)
    require(lower - margin <= upper + 1e-10, "LOWER_EXCEEDS_FEASIBLE_UPPER")
    require(
        candidate["solution"]["multiplier_evaluations"] <= 96
        and candidate["solution"]["ball_root_iteration_max"] <= 80,
        "SOLVER_WORK_CAP",
    )
    feasible = np.linalg.norm(u) <= 1 + 1e-10 and row["R"] <= 1 + 1e-10
    admitted = feasible and row["N"] <= 0.999 - 1e-8 and row["F"] <= 0.999 - 1e-8
    return dict(
        checked=True,
        feasible=bool(feasible),
        threshold_candidate=bool(admitted),
        native_target_excluded=bool(
            feasible and lower - margin > 0.999 and width <= 1e-7
        ),
        optimality="CERTIFIED_NARROW_BOUND" if width <= 1e-7 else "UNKNOWN",
        upper=upper,
        conservative_lower=lower - margin,
        bound_width=width,
        raw_points=values,
        rank=len(u),
        parameter_orthogonality=float(orth),
        stationarity=float(np.linalg.norm(B @ u + a)),
        producer_or_optimizer_calls=0,
    )
