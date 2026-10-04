"""Independent original-block checks of actual saved consumer vectors.

No inverse/factor/solve: exported inverse actions are checked by multiplying
the original blocks, and complete port actions are rebuilt from saved B/D.
"""

import numpy as np


def ratio(a, b):
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("W1_FINITE_MATCHED_SAVED_VECTORS")
    numerator, ref = float(np.linalg.norm(a - b)), float(np.linalg.norm(b))
    den = max(ref, np.finfo(float).tiny)
    return {
        "numerator": numerator,
        "reference_norm": ref,
        "denominator": den,
        "relative": numerator / den,
        "near_zero": bool(ref <= np.finfo(float).tiny),
    }


def local_equations(a, report, modes):
    p, side = report["degree"], report["side"]
    if p not in (4, 6) or side not in ("top", "bottom"):
        raise ValueError("W1_LOCAL_P_SIDE")
    dim, ni = 3 * p * (p + 1) ** 2, 108 if p == 4 else 450
    ii, tt = a["interior_positions"], a["trace_positions"]
    if (
        ii.dtype.kind not in "iu"
        or tt.dtype.kind not in "iu"
        or len(ii) != ni
        or len(tt) != dim - ni
        or not np.array_equal(np.sort(np.r_[ii, tt]), np.arange(dim))
    ):
        raise ValueError("W1_COMPLETE_UNIQUE_NATIVE_PARTITION")
    if (
        int(a["degree"]) != p
        or str(a["side"]) != side
        or int(a["quadrature_degree"]) != 60
    ):
        raise ValueError("W1_SAVED_P_SIDE_Q_IDENTITY")
    expected = np.array(
        [i for i, m in enumerate(modes) if m["side"] == side], dtype=np.int64
    )
    indices = a["active_mode_indices"]
    if not np.array_equal(indices, expected) or len(a["mode_alpha"]) != len(modes):
        raise ValueError("W1_LOCAL_FULL_MODE_ORDER")
    keys = np.array(
        [
            [
                m["m"],
                m["n"],
                0 if m["side"] == "top" else 1,
                0 if m["polarization"] == "s" else 1,
            ]
            for m in modes
        ],
        dtype=np.int64,
    )
    H = np.array([m["projection_denominator"] for m in modes])
    if not np.array_equal(keys, a["mode_keys"]) or not np.array_equal(
        H, a["original_H"]
    ):
        raise ValueError("W1_LOCAL_KEY_ORIGINAL_H")
    V = a["local_native_tensor"]
    if V.shape != (dim, dim):
        raise ValueError("W1_LOCAL_COMPLETE_TENSOR")
    Vii, Vit, Vti, Vtt = (
        V[np.ix_(ii, ii)],
        V[np.ix_(ii, tt)],
        V[np.ix_(tt, ii)],
        V[np.ix_(tt, tt)],
    )
    Bi, Bt, Di, Dt = [
        a[name] for name in ("saved_Bi", "saved_Bt", "saved_Di", "saved_Dt")
    ]
    for array, width in ((Bi, ni), (Di, ni), (Bt, dim - ni), (Dt, dim - ni)):
        if array.shape != (len(indices), width) or not np.isfinite(array).all():
            raise ValueError("W1_LOCAL_ALL_COLUMNS_REQUIRED")
    alpha, xt, xi = a["mode_alpha"], a["trace_values"], a["recovered_interior"]
    fi, ft = a["interior_rhs"], a["trace_rhs"]
    sB, sf, st, sVit = [
        a[k]
        for k in (
            "solve_internal_B",
            "solve_internal_rhs",
            "solve_internal_trace",
            "solve_Vit",
        )
    ]
    bi, bt = Bi.T @ alpha[indices], Bt.T @ alpha[indices]

    def port(v):
        out = np.zeros(len(modes), np.complex128)
        out[indices] = Di @ v
        return out

    dt = np.zeros(len(modes), np.complex128)
    dt[indices] = Dt @ xt
    qhat, affine = alpha + port(sB), a["port_rhs"] + port(sf)
    Schur = Vtt - Vti @ sVit
    bhat, fhat = bt - Vti @ sB, ft - Vti @ sf
    original_t = Vti @ xi + Vtt @ xt + bt - ft
    reduced_t = (
        a["reduced_trace_matrix"] @ xt
        + a["reduced_trace_B_alpha"]
        - a["reduced_trace_rhs"]
    )
    original_p = alpha - port(xi) - dt - a["port_rhs"]
    reduced_p = a["qhat_alpha"] - a["affine_internal_rhs"] - dt + port(st)
    checks = {
        "Bi_alpha_actual": (a["Bi_alpha"], bi),
        "Bt_alpha_actual": (a["Bt_alpha"], bt),
        "inverse_B_original_block": (Vii @ sB, bi),
        "inverse_rhs_original_block": (Vii @ sf, fi),
        "inverse_trace_original_block": (Vii @ st, Vit @ xt),
        "inverse_Vit_original_block": (Vii @ sVit, Vit),
        "qhat_alpha_actual": (a["qhat_alpha"], qhat),
        "affine_internal_rhs_actual": (a["affine_internal_rhs"], affine),
        "recovered_interior_action": (xi, sf - st - sB),
        "interior_original_equation": (Vii @ xi + Vit @ xt + bi, fi),
        "trace_original_equation": (Vti @ xi + Vtt @ xt + bt, ft),
        "trace_reduced_equation": (
            a["reduced_trace_matrix"] @ xt + a["reduced_trace_B_alpha"],
            a["reduced_trace_rhs"],
        ),
        "Schur_actual": (a["reduced_trace_matrix"], Schur),
        "Bhat_actual": (a["reduced_trace_B_alpha"], bhat),
        "fhat_actual": (a["reduced_trace_rhs"], fhat),
        "port_original_equation": (alpha - port(xi) - dt, a["port_rhs"]),
        "port_reduced_equation": (
            a["qhat_alpha"] - dt + port(st),
            a["affine_internal_rhs"],
        ),
        "full_internal_recovery": (xi, a["known_interior_solution"]),
        "port_internal_B_correction": (a["port_internal_B_correction"], port(sB)),
        "port_internal_rhs_correction": (a["port_internal_rhs_correction"], port(sf)),
        "port_internal_trace_correction": (
            a["port_internal_trace_correction"],
            port(st),
        ),
        "port_internal_recovered_correction": (
            a["port_internal_recovered_correction"],
            port(xi),
        ),
        "port_trace_action": (a["port_trace_action"], dt),
        "saved_original_trace_residual": (a["original_trace_residual"], original_t),
        "saved_reduced_trace_residual": (a["reduced_trace_residual"], reduced_t),
        "saved_original_port_residual": (a["port_residual"], original_p),
        "saved_reduced_port_residual": (a["reduced_port_residual"], reduced_p),
    }
    # Residual-vector comparisons use the unchanged original equation scale,
    # rather than division by an almost-zero residual itself.
    metrics = {}
    for name, (actual, reference) in checks.items():
        if name.startswith("saved_"):
            scale = max(
                float(np.linalg.norm(ft if "trace" in name else alpha)),
                np.finfo(float).tiny,
            )
            numerator = float(np.linalg.norm(actual - reference))
            value = {
                "numerator": numerator,
                "denominator": scale,
                "relative": numerator / scale,
                "reference_norm": float(np.linalg.norm(reference)),
                "near_zero": False,
            }
        else:
            value = ratio(actual, reference)
        metrics[name] = value
    for name, left, right, scale in (
        (
            "trace_elimination_identity",
            original_t,
            reduced_t,
            max(np.linalg.norm(ft), np.linalg.norm(Vtt @ xt)),
        ),
        (
            "port_elimination_identity",
            original_p,
            reduced_p,
            max(np.linalg.norm(alpha), np.linalg.norm(a["port_rhs"])),
        ),
    ):
        numerator = float(np.linalg.norm(left - right))
        den = max(float(scale), np.finfo(float).tiny)
        metrics[name] = {
            "numerator": numerator,
            "denominator": den,
            "reference_norm": float(scale),
            "relative": numerator / den,
            "near_zero": bool(scale <= np.finfo(float).tiny),
        }
    limits = {
        name: (
            1e-10
            if name
            in {
                "interior_original_equation",
                "trace_original_equation",
                "trace_reduced_equation",
                "port_original_equation",
                "port_reduced_equation",
                "Bi_alpha_actual",
                "Bt_alpha_actual",
            }
            else 1e-11
        )
        for name in metrics
    }
    return {
        "metrics": metrics,
        "limits": limits,
        "pass": all(m["relative"] <= limits[name] for name, m in metrics.items()),
        "full_mode_count": len(modes),
        "all_native_columns": dim,
        "checker_factor_calls": 0,
        "checker_solve_calls": 0,
    }


def coordinate_checks(centered, absolute, k, e, traction, H, alpha, origins, planes):
    origins = np.asarray(origins)
    if origins.shape != (2, 3) or not np.array_equal(
        origins[1] - origins[0], [25, 12.5, 0]
    ):
        raise ValueError("W1_PHYSICAL_TRANSLATION_REQUIRED")
    if not np.array_equal(planes, [130, -10]) or np.any(np.asarray(k)[:, :2].imag != 0):
        raise ValueError("W1_REFERENCE_PLANE_REAL_TANGENTIAL_SCOPE")
    phase = np.exp(1j * (np.asarray(k) @ np.array([25, 12.5, 0])))
    Bc = np.einsum("mjc,mc->mj", centered, -traction[:, :2])
    Ba = np.einsum("mjc,mc->mj", absolute, -traction[:, :2])
    Dc = np.einsum("mjc,mc->mj", centered, e[:, :2]).conj() / H[:, None]
    Da = np.einsum("mjc,mc->mj", absolute, e[:, :2]).conj() / H[:, None]
    reverse = 1 / phase
    v = np.exp(0.117j * np.arange(centered.shape[1]))
    metrics = {
        "integral_translation": ratio(absolute, centered * phase[:, None, None]),
        "B_physical_alpha": ratio(Ba * (alpha * reverse)[:, None], Bc * alpha[:, None]),
        "D_original_H_projection": ratio(Da @ v, reverse * (Dc @ v)),
        "B_adjoint": ratio(Ba.conj() @ v, phase.conj() * (Bc.conj() @ v)),
    }
    return metrics


def oracle_checks(document, required_frequencies):
    from decimal import Decimal

    if document.get("scope") != {
        "maximum_abs_omega": 56,
        "maximum_degree": 6,
        "precision": [80, 110],
        "Gauss_points": 64,
    }:
        raise ValueError("W1_ORACLE_FIXED_SCOPE")
    checks = document["checks"]
    if sorted(row["omega"] for row in checks) != sorted(required_frequencies):
        raise ValueError("W1_ORACLE_FREQUENCY_COVERAGE")
    maximum = 0.0
    for row in checks:
        if not np.isfinite(row["omega"]) or abs(row["omega"]) > 56:
            raise ValueError("ORACLE_ACCURACY_UNRESOLVED")

        def complex_values(name):
            values = row[name]
            if len(values) != 7:
                raise ValueError("W1_ORACLE_ALL_MOMENTS")
            out = []
            for real, imag in values:
                if not Decimal(real).is_finite() or not Decimal(imag).is_finite():
                    raise ValueError("W1_ORACLE_NONFINITE_DECIMAL")
                out.append(complex(float(Decimal(real)), float(Decimal(imag))))
            return np.array(out)

        analytic = np.array([complex(*z) for z in row["analytic_values"]])
        b, c = (
            complex_values("Decimal80_values"),
            complex_values("Decimal110_Gauss64_values"),
        )
        error = max(float(np.max(abs(analytic - b))), float(np.max(abs(b - c))))
        if not np.isfinite(error):
            raise ValueError("W1_ORACLE_NONFINITE")
        maximum = max(maximum, error)
    return {
        "status": "ORACLE_INTERVAL_PASS"
        if maximum <= 1e-12
        else "ORACLE_ACCURACY_UNRESOLVED",
        "maximum_absolute": maximum,
        "checks": len(checks),
    }


def incident_checks(data, rebuilt):
    """Original physical load, including shifted coordinates and background."""
    for name in (
        "k_in",
        "k_out",
        "e_in",
        "physical_alpha",
        "origin_center",
        "origin_absolute",
        "reference_plane_nm",
        "scope",
    ):
        if not np.array_equal(data[name], rebuilt[name]):
            raise ValueError("W1_ACTUAL_INCIDENT_PHYSICAL_IDENTITY:" + name)
    metrics = {
        name: ratio(data[name], rebuilt["rhs_reference"])
        for name in (
            "rhs_center",
            "rhs_reference",
            "rhs_absolute",
            "rhs_absolute_reference",
            "rhs_modal",
            "background_rhs_center",
            "background_rhs_absolute",
        )
    }
    for name in ("background_r", "background_t", "background_bottom_k"):
        metrics[name] = ratio(data[name], rebuilt[name])
    for name in ("background_interface_E_jump", "background_interface_curl_jump"):
        numerator = float(abs(data[name]))
        denominator = float(np.linalg.norm(rebuilt["k_in"]))
        metrics[name] = {
            "numerator": numerator,
            "denominator": denominator,
            "relative": numerator / denominator,
        }
    return metrics
