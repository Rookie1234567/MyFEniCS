"""Small reference-exposed diagnostics; never a solver or training objective.

The weighted QR uses column scales, deterministic pivots and two passes of
modified Gram--Schmidt. Only the small rectangular R undergoes SVD. Real
parameter columns are projected with real coefficients, including complex FE
fields. No normal-equation inverse is used.
"""

import numpy as np


def inner(x, wx, *, real=False):
    value = np.asarray(x).conj().T @ np.asarray(wx)
    return value.real if real else value


def energy(x, wx, *, operation_scale=0.0):
    x, wx = np.asarray(x), np.asarray(wx)
    value = np.vdot(x, wx)
    scale = float(np.linalg.norm(x) * np.linalg.norm(wx))
    tolerance = (
        256 * np.finfo(float).eps * max(scale, operation_scale, np.finfo(float).tiny)
    )
    if not np.isfinite(value) or value.real < -tolerance or abs(value.imag) > tolerance:
        raise ValueError("INVALID_HERMITIAN_ENERGY")
    return max(0.0, float(value.real))


def quadratic_change(old, delta, wold, wdelta):
    """Retain signed cross term and operation-scaled reconstruction defect."""
    before = energy(old, wold)
    after = energy(old + delta, wold + wdelta)
    cross = 2 * float(np.vdot(old, wdelta).real)
    update = energy(delta, wdelta)
    actual = after - before
    scale = max(before, after, abs(cross) + update, np.finfo(float).tiny)
    return dict(
        before=before,
        after=after,
        cross=cross,
        update_energy=update,
        change=actual,
        reconstructed_change=cross + update,
        operation_scale=scale,
        defect=abs(actual - cross - update) / scale,
    )


def frozen_direction_attribution(raw, alpha, native_denominator):
    """Two endpoints of ONE already frozen direction; no new step selection."""
    alpha = np.asarray(alpha)
    if alpha.ndim != 1 or np.iscomplexobj(alpha) or not np.isfinite(alpha).all():
        raise ValueError("FROZEN_REAL_ALPHA_REQUIRED")
    if not np.isfinite(native_denominator) or native_denominator <= 0:
        raise ValueError("ORIGINAL_NATIVE_DENOMINATOR_REQUIRED")
    rows = {}
    for name, old, delta, wold, wdelta in (
        ("F", raw["e"], raw["X"] @ alpha, raw["Ge"], raw["GX"] @ alpha),
        ("R", raw["r"], raw["Y"] @ alpha, raw["qr"], raw["WY"] @ alpha),
        ("N", raw["r"], raw["Y"] @ alpha, raw["r"], raw["Y"] @ alpha),
    ):
        values = quadratic_change(old, delta, wold, wdelta)
        scale = np.linalg.norm(old) * np.linalg.norm(wold)
        if values["before"] <= 256 * np.finfo(float).eps * scale:
            raise ValueError("UNRESOLVED_DIRECTION_DENOMINATOR")
        b = values["cross"] / values["before"]
        c = values["update_energy"] / values["before"]
        at_one = values["after"] / values["before"]
        b_error = 256 * np.finfo(float).eps * 2 * np.linalg.norm(old) * np.linalg.norm(wdelta) / values["before"]
        c_error = 256 * np.finfo(float).eps * np.linalg.norm(delta) * np.linalg.norm(wdelta) / values["before"]
        endpoint_defect = abs(at_one - (1 + b + c)) / max(1, abs(b) + abs(c), abs(at_one))
        if values["defect"] > 1e-10 or endpoint_defect > 1e-10:
            raise ValueError("DIRECTION_ENDPOINT_PAIRING")
        rows[name] = dict(**values, b=float(b), c=float(c), b_roundoff=float(b_error),
                          c_roundoff=float(c_error), at_zero=1., at_one=float(at_one),
                          endpoint_reconstruction_defect=float(endpoint_defect))
    native = rows["N"]
    classification = "UNKNOWN"
    intersection = None
    if native["b"] > native["b_roundoff"] and native["c"] >= -native["c_roundoff"]:
        classification = "DIRECTION_NATIVE_CONFLICT"
    elif native["b"] < -native["b_roundoff"] and native["at_one"] > 1 + 1e-10:
        classification = "LINEAR_STEP_OVERSHOOT"
        if native["c"] > native["c_roundoff"]:
            intersection = float(-native["b"] / native["c"])
    return dict(norms=rows, classification=classification,
                analytic_nonzero_intersection_diagnostic_only=intersection,
                native_denominator=float(native_denominator),
                native_before=float(np.sqrt(native["before"]) / native_denominator),
                native_at_saved_step=float(np.sqrt(native["after"]) / native_denominator),
                evaluated_s=[0, 1], new_candidate_generated=False,
                value_kind="DERIVED_LOCAL_LINEAR_MODEL", true_NN_increment=False)


def weighted_qr(columns, weighted_columns, *, real=True, qr_tol=1e-14):
    X, WX = np.asarray(columns), np.asarray(weighted_columns)
    if X.ndim != 2 or X.shape != WX.shape or X.shape[1] > 16:
        raise ValueError("BOUNDED_PAIRED_COLUMN_LAYOUT_REQUIRED")
    if not np.isfinite(X).all() or not np.isfinite(WX).all():
        raise ValueError("NONFINITE_DIAGNOSTIC_COLUMNS")
    n = X.shape[1]
    scales = np.array([np.sqrt(energy(X[:, j], WX[:, j])) for j in range(n)])
    nonzero = scales > 0
    safe = np.where(nonzero, scales, 1)
    U, WU = X / safe, WX / safe
    dtype = np.float64 if real else np.complex128
    Q, WQ, T, pivots = [], [], [], []
    remaining = list(np.flatnonzero(nonzero))
    while remaining:
        candidates = []
        for j in remaining:
            v, wv = U[:, j].copy(), WU[:, j].copy()
            t = np.eye(n, dtype=dtype)[:, j] / safe[j]
            for _ in range(2):
                for q, wq, tq in zip(Q, WQ, T, strict=True):
                    a = np.vdot(q, wv)
                    a = float(a.real) if real else a
                    v -= q * a
                    wv -= wq * a
                    t -= tq * a
            # v and Wv have each undergone cancellation of unit-scale terms.
            # Their original operation scale, rather than the tiny remainder,
            # bounds roundoff; substantial invalid input remains rejected.
            operation_scale = float(np.linalg.norm(U[:, j]) * np.linalg.norm(WU[:, j]))
            norm = np.sqrt(energy(v, wv, operation_scale=operation_scale))
            candidates.append((norm, j, v, wv, t))
        norm, j, v, wv, t = max(candidates, key=lambda row: (row[0], -row[1]))
        if norm <= qr_tol:
            break
        Q.append(v / norm)
        WQ.append(wv / norm)
        T.append(t / norm)
        pivots.append(int(j))
        remaining.remove(j)
    Q = np.column_stack(Q) if Q else np.empty((len(X), 0), complex)
    WQ = np.column_stack(WQ) if WQ else np.empty_like(Q)
    T = np.column_stack(T) if T else np.empty((n, 0), dtype=dtype)
    R = inner(Q, WU, real=real)
    orth = inner(Q, WQ, real=real) - np.eye(Q.shape[1])
    residual, wresidual = U - Q @ R, WU - WQ @ R
    defect = np.sqrt(
        sum(
            energy(
                residual[:, j],
                wresidual[:, j],
                operation_scale=float(
                    np.linalg.norm(U[:, j]) * np.linalg.norm(WU[:, j])
                ),
            )
            for j in range(n)
        )
    )
    return dict(
        Q=Q,
        WQ=WQ,
        T=T,
        R=R,
        scales=scales,
        pivots=pivots,
        QR_rank=Q.shape[1],
        G_orthogonality=float(np.linalg.norm(orth)),
        normalized_reconstruction=float(
            defect / max(np.sqrt(np.count_nonzero(nonzero)), 1)
        ),
        zero_columns=np.flatnonzero(~nonzero).tolist(),
        real_coefficients=real,
    )


def project_real(columns, weighted_columns, target, weighted_target, *, rcond=1e-10):
    qr = weighted_qr(columns, weighted_columns, real=True)
    U, sigma, VH = np.linalg.svd(qr["R"], full_matrices=False)
    retained = sigma > (rcond * sigma[0] if len(sigma) else 0)
    rhs = inner(qr["Q"], weighted_target, real=True)
    beta = (
        VH[retained].T @ ((U[:, retained].T @ rhs) / sigma[retained])
        if np.any(retained)
        else np.zeros(columns.shape[1])
    )
    alpha = beta / np.where(qr["scales"] > 0, qr["scales"], 1)
    delta, wdelta = columns @ alpha, weighted_columns @ alpha
    before = energy(target, weighted_target)
    after = energy(target - delta, weighted_target - wdelta)
    normal = inner(columns, weighted_target - wdelta, real=True)
    scale = max(np.linalg.norm(qr["scales"]) * np.sqrt(before), np.finfo(float).tiny)
    retained_normal = U[:, retained].T @ (rhs - qr["R"] @ beta)
    record = dict(
        rank=int(np.count_nonzero(retained)),
        singular_values=sigma.tolist(),
        rcond=rcond,
        truncation=(~retained).tolist(),
        coefficients=alpha.tolist(),
        before_energy=before,
        after_energy=after,
        removed_energy_fraction=(before - after) / before if before else None,
        full_optimality=float(np.linalg.norm(normal) / scale),
        retained_optimality=float(
            np.linalg.norm(retained_normal)
            / max(np.linalg.norm(rhs), np.finfo(float).tiny)
        ),
        nonincrease=bool(after <= before + 1e-10 * max(before, 1)),
        QR_rank=qr["QR_rank"],
        pivots=qr["pivots"],
        G_orthogonality=qr["G_orthogonality"],
        normalized_reconstruction=qr["normalized_reconstruction"],
        zero_columns=qr["zero_columns"],
        real_coefficients=True,
    )
    return alpha, delta, record
