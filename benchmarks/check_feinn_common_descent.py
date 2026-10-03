"""Independent raw-array checker. No optimization, solver or network imports."""

import numpy as np


def need(condition, message):
    if not condition:
        raise ValueError(message)


def same(x, y, tolerance=1e-8):
    x, y = np.asarray(x), np.asarray(y)
    need(x.shape == y.shape and np.isfinite(x).all() and np.isfinite(y).all(), "CHECKER_SHAPE_FINITE")
    need(np.linalg.norm(x - y) <= tolerance * max(1, np.linalg.norm(x), np.linalg.norm(y)), "CHECKER_VALUE")


def classify(F, R, lower, margin, valid):
    if not valid:
        return "UNKNOWN"
    if max(F, R) <= 0.999 - 1e-10:
        return "COMMON_DESCENT_AT_LEAST_0P1_PERCENT"
    if lower - margin > 0.999 + 1e-10:
        return "NO_0P1_PERCENT_COMMON_DESCENT_IN_RETAINED_BALL"
    return "UNKNOWN_THRESHOLD_BRACKET"


def verify_configuration(record, raw, metadata, theta_norm, native_denominator):
    """Recompute physical steps, spectra/duality and provenance from raw arrays."""
    state, subset = record["state"], record["subset"]
    need(state == metadata["name"] and subset in ("PDE8", "ALL16"), "STATE_IDENTITY")
    need(record["state_identity"] == metadata["identity"], "STATE_HASH_IDENTITY")
    active = [d for d in metadata["directions"] if "column" in d]
    need(sorted(d["column"] for d in active) == list(range(raw["P"].shape[1])), "RAW_COLUMN_MAP")
    need(all(d["kind"] in ("PDE", "reference_G") for d in active), "RAW_COLUMN_KIND")
    columns = sorted(d["column"] for d in active if subset == "ALL16" or d["kind"] == "PDE")
    need(record["columns"] == columns, "COLUMN_PROVENANCE")
    need(record["residual_candidate_unlabeled"] == (subset == "PDE8"), "LABEL_ROLE")
    selected = {k: v[:, columns] if k in ("P", "X", "GX", "Y", "WY") else v for k, v in raw.items()}
    for value in selected.values():
        need(np.isfinite(value).all(), "RAW_NONFINITE")
    P, T = selected["P"], np.asarray(record["T"], float)
    need(P.dtype == np.float64 and not np.iscomplexobj(T), "REAL_PARAMETER")
    rho = 1e-3 * max(theta_norm, 1)
    same(record["rho"], rho, 1e-12)
    need(record["rcond"] in (1e-10, 1e-12), "RCOND_CONTRACT")
    scales = np.linalg.norm(P, axis=0)
    safe = np.where(scales > 0, scales, 1)
    U, sigma, _ = np.linalg.svd(P / safe, full_matrices=False)
    keep = sigma > (record["rcond"] * sigma[0] if len(sigma) else 0)
    need(record["basis"]["rank"] == int(keep.sum()) and T.shape == (len(columns), int(keep.sum())), "RANK_LAYOUT")
    need(record["basis"]["truncation"] == (~keep).tolist(), "TRUNCATION")
    same(record["basis"]["singular_values"], sigma, 1e-10)
    same(record["basis"]["column_scales"], scales, 1e-10)
    Q = P @ T
    orth = np.linalg.norm(Q.T @ Q - np.eye(Q.shape[1]))
    need(orth <= 1e-10, "RAW_PARAMETER_ORTHOGONALITY")
    same(record["basis"]["parameter_orthogonality"], orth, 1e-10)
    same(Q @ (Q.T @ U[:, keep]), U[:, keep], 1e-10)
    reconstruction = np.linalg.norm(P / safe - Q @ (Q.T @ (P / safe))) / max(np.linalg.norm(P / safe), 1)
    same(record["basis"]["parameter_reconstruction"], reconstruction, 1e-10)
    quadratics = {}
    for key, col, wcol, t, wt in (("F", "X", "GX", "e", "Ge"), ("R", "Y", "WY", "r", "qr")):
        x, wx = selected[t], selected[wt]
        d = np.vdot(x, wx)
        need(d.real > 256 * np.finfo(float).eps * np.linalg.norm(x) * np.linalg.norm(wx), "RAW_DENOMINATOR")
        need(abs(d.imag) <= 256 * np.finfo(float).eps * np.linalg.norm(x) * np.linalg.norm(wx), "RAW_ENERGY_IMAGINARY")
        C, WC = rho * selected[col] @ T, rho * selected[wcol] @ T
        Hfull = C.conj().T @ WC / d.real
        need(np.linalg.norm(Hfull - Hfull.conj().T) <= 1e-10 * max(np.linalg.norm(Hfull), np.finfo(float).tiny), "RAW_HERMITIAN")
        H = (Hfull.real + Hfull.real.T) / 2
        a = (C.conj().T @ wx).real / d.real
        stored = record["quadratic_" + key]
        same(stored["denominator"], d.real, 1e-12)
        same(stored["H"], H, 1e-10)
        same(stored["a"], a, 1e-10)
        same(stored["eigenvalues"], np.linalg.eigvalsh(H), 1e-10)
        need(not len(a) or np.linalg.eigvalsh(H)[0] >= -256 * np.finfo(float).eps * np.linalg.norm(H, 2), "RAW_PSD")
        quadratics[key] = (H, a)
    worst = 0.0
    for name, row in record["points"].items():
        u, alpha = np.asarray(row["u"]), np.asarray(row["alpha"])
        need(np.linalg.norm(u) <= 1 + 1e-10, "BALL_FEASIBILITY")
        same(alpha, rho * T @ u, 1e-10)
        step = np.linalg.norm(P @ alpha)
        need(step <= rho * (1 + 1e-10), "PARAMETER_RADIUS")
        same(row["parameter_step_norm"], step, 1e-10)
        for key, col, wcol, t, wt in (("F", "X", "GX", "e", "Ge"), ("R", "Y", "WY", "r", "qr")):
            x, wx = selected[t], selected[wt]
            delta, wdelta = selected[col] @ alpha, selected[wcol] @ alpha
            before = np.vdot(x, wx).real
            after = np.vdot(x + delta, wx + wdelta).real
            cross, update = 2 * np.vdot(x, wdelta).real, np.vdot(delta, wdelta).real
            same(row[key], after / before, 1e-10)
            for field, value in (("before", before), ("after", after), ("signed_cross", cross), ("update", update)):
                same(row[key + "_energy"][field], value, 1e-10)
            defect = abs(after - before - cross - update) / max(before, abs(cross) + abs(update))
            need(defect <= 1e-8, "RAW_CROSS_RECONSTRUCTION")
            worst = max(worst, defect)
            H, a = quadratics[key]
            same(row[key], 1 + 2 * a @ u + u @ H @ u, 1e-8)
        same(row["native_linear"], np.linalg.norm(selected["r"] + selected["Y"] @ alpha) / native_denominator, 1e-10)
        if name in ("residual", "field"):
            key = "R" if name == "residual" else "F"
            H, a = quadratics[key]
            mu = record["common"]["endpoint_multipliers"][key]
            need(np.isfinite(mu) and mu >= 0, "ENDPOINT_MULTIPLIER")
            need(np.linalg.norm((H + mu * np.eye(len(u))) @ u + a) <= 1e-8 * max(1, np.linalg.norm(a), np.linalg.norm(H)), "ENDPOINT_STATIONARITY")
            need(abs(mu * (u @ u - 1)) <= 1e-8 * max(1, mu), "ENDPOINT_COMPLEMENTARITY")
    common = record["common"]
    u = np.asarray(common["u"])
    same(u, record["points"]["common"]["u"], 1e-12)
    upper = max(record["points"]["common"]["F"], record["points"]["common"]["R"])
    same(common["U"], upper, 1e-10)
    certificate = common["certificate"]
    weight, mu = certificate["lambda_"], certificate["mu"]
    need(np.isfinite(weight) and np.isfinite(mu) and 0 <= weight <= 1 and mu >= 0, "DUAL_MULTIPLIERS")
    HF, aF = quadratics["F"]
    HR, aR = quadratics["R"]
    H, a = weight * HF + (1 - weight) * HR, weight * aF + (1 - weight) * aR
    M = H + mu * np.eye(len(a))
    spectrum = np.linalg.eigvalsh(M)
    need(not len(a) or spectrum[0] >= 0, "DUAL_PSD")
    same(certificate["spectrum"], spectrum, 1e-10)
    # Independent dense solve only of the <=16 by16 saved certificate matrix.
    if len(a) and spectrum[0] > 0:
        z = np.linalg.solve(M, a)
    else:
        z = np.linalg.lstsq(M, a, rcond=1e-14)[0] if len(a) else np.empty(0)
    same(certificate["inverse_action"], z, 1e-8)
    range_defect = np.linalg.norm(M @ np.asarray(certificate["inverse_action"]) - a)
    same(certificate["range_defect"], range_defect, 1e-8)
    need(range_defect <= 1e-8 * max(1, np.linalg.norm(a)), "DUAL_RANGE")
    lower = 1 - mu - a @ z
    same(certificate["lower"], lower, 1e-8)
    margin = 4096 * np.finfo(float).eps * (1 + abs(mu) + np.linalg.norm(H) + np.linalg.norm(a) * np.linalg.norm(certificate["inverse_action"])) + 4 * range_defect * max(1, np.linalg.norm(certificate["inverse_action"]))
    same(certificate["numerical_margin"], margin, 1e-10)
    need(certificate["numerical_margin"] >= 0, "NUMERICAL_MARGIN")
    same(common["gap"], upper - certificate["lower"], 1e-8)
    need(upper + certificate["numerical_margin"] >= certificate["lower"] - 1e-10, "BOUND_ORDER")
    same(certificate["stationarity"], np.linalg.norm(M @ u + a), 1e-10)
    same(certificate["complementarity"], abs(mu * (u @ u - 1)), 1e-10)
    need(common["lambda_evaluations"] <= 64 and common["root_iteration_max"] <= 80, "ITERATION_CAP")
    valid = reconstruction <= 1e-10 and worst <= 1e-8
    result = classify(record["points"]["common"]["F"], record["points"]["common"]["R"], certificate["lower"], certificate["numerical_margin"], valid)
    need(record["classification"] == result, "FALSE_PRODUCER_CLASSIFICATION")
    need(record["bounds_closed"] == (common["gap"] + certificate["numerical_margin"] <= 1e-8), "BOUND_GAP_STATUS")
    need(not record["true_NN_increment"] and not record["official_candidate_results"], "DIAGNOSTIC_LABEL")
    return dict(state=state, subset=subset, rcond=record["rcond"], classification=result,
                U=upper, L=float(lower), margin=float(certificate["numerical_margin"]), raw_cross_defect=worst)
