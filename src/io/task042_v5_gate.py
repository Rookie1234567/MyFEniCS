"""Independent V5 checks from saved raw vectors/norms, without FE or solvers."""

import math

import numpy as np
from scipy.linalg import blas

TOL = 1e-10


def check_same_residual(record, arrays):
    r = arrays["r"]
    rn = float(np.linalg.norm(r))

    def ratio(x):
        return float(np.linalg.norm(x)) / rn if rn else float(np.linalg.norm(x))

    report = record["report"]
    defects = []
    for name in ("B", "C", "B2"):
        d = report["directions"][name]
        image = arrays["S_" + name]
        alpha = complex(*d["alpha"])
        defects.extend(
            (
                abs(d["rho_unit"] - ratio(r - image)),
                abs(d["rho_opt"] - ratio(r - alpha * image)),
            )
        )
    for name in ("BC_LS", "ZB_LS"):
        value = report["rho_BC" if name == "BC_LS" else "rho_ZB"]
        defects.append(abs(value - ratio(arrays["remaining_" + name])))
    eta = ratio(arrays["E_r"])
    defects.append(abs(report["coverage_r"]["eta"] - eta))
    if rn:
        defects.extend(
            (
                report["rho_ZB"] - report["rho_BC"],
                report["rho_BC"] - report["directions"]["B"]["rho_opt"],
                report["rho_ZB"] - eta,
            )
        )
    for name, audit in record["corrected_audits"].items():
        norms = audit["original_norms"]
        native = (
            norms["native_absolute"] / norms["native_scale"]
            if norms["native_scale"]
            else norms["native_absolute"]
        )
        defects.extend(
            (
                abs(native - audit["native_relative"]),
                abs(audit["rho_same_residual"] - ratio(arrays["remaining_" + name])),
            )
        )
        if not norms["finite"] or norms["maximum_slave_storage"]:
            raise ValueError("diagnostic original field nonfinite/slave invalid")
        defects.extend(audit["checks"].values())
    if not all(math.isfinite(v) for v in defects) or max(defects) > TOL:
        raise ValueError("V5 independent same-vector/LS/original audit gate failed")
    return {
        "passed": True,
        "max_defect_or_inclusion_violation": max(defects),
        "limit": TOL,
    }


def check_complement(record, arrays, u=None):
    y, t, p, v, w = (arrays[k] for k in ("HV", "TV", "Pi_HV", "V", "w"))

    def norm(a):
        return float(np.linalg.norm(a))

    def ratio(a, scale):
        return norm(a) / scale if scale else norm(a)

    errors = [
        ratio(y - t - p, norm(y)),
        ratio(v.conj().T @ v - np.eye(v.shape[1]), np.sqrt(v.shape[1])),
    ]
    if u is not None:
        # Reuse frozen U only in this read-only checker, never form UU^H.
        uh_v = np.column_stack(
            [blas.zgemv(1.0, u, v[:, j], trans=2) for j in range(v.shape[1])]
        )
        errors.append(ratio(uh_v, np.sqrt(v.shape[1])))
        projected = np.column_stack(
            [u @ blas.zgemv(1.0, u, y[:, j], trans=2) for j in range(y.shape[1])]
        )
        errors.append(ratio(projected - p, norm(y)))
    for key, data in (
        ("HV_singular_values", y),
        ("TV_singular_values", t),
        ("Pi_HV_singular_values", p),
    ):
        actual = np.linalg.svd(data, compute_uv=False)
        errors.append(ratio(actual - np.asarray(record[key]), norm(actual)))
    errors.extend(
        (
            ratio(arrays["Hv"] - y @ w, norm(arrays["Hv"])),
            ratio(arrays["Tv"] - t @ w, norm(arrays["Hv"])),
            ratio(arrays["SB2v"] - arrays["Tv"], norm(arrays["Hv"])),
        )
    )
    witness = record["witness"]
    errors.extend(
        abs(norm(arrays[k]) - witness[value]) / max(norm(arrays[k]), 1.0)
        for k, value in (
            ("Hv", "HV_absolute"),
            ("Tv", "TV_absolute"),
            ("Pi_Hv", "Pi_HV_absolute"),
        )
    )
    if not all(math.isfinite(a) for a in errors) or max(errors) > TOL:
        raise ValueError("V5 independent complete-image probe check failed")
    return {
        "passed": True,
        "max_complete_image_defect": max(errors),
        "limit": TOL,
        "global_singularity_inferred": False,
    }
