"""Independent matrix/vector checker of a saved finite native recovery pack.

No production action, recovery method, solver, factorization or status field
is used to recompute the gates. The original tiny CSR is an unfactored oracle.
"""

import numpy as np
from scipy.sparse import csr_matrix

from benchmarks.check_boundary_witness import metric


def independent_expansion(lit, n):
    offsets, rows, dual = (
        lit[k] for k in ("master_offsets", "master_rows", "master_dual_coefficients")
    )
    if offsets.shape != (n + 1,) or offsets[-1] != len(rows) or len(rows) != len(dual):
        raise ValueError("complete literal constraint inventory")
    return csr_matrix((dual.conjugate(), rows, offsets), shape=(n, n))


def audit_packets(store):
    geometry, lit = store.read("geometry")
    system, numbering = store.read("system")
    _, sparse = store.read("oracle")
    qrow, quad = store.read("quadrature")
    _, d = store.read("recovery")
    if store.expected_contract is not None:
        from src.solvers.bounded_port_provider import content_hash
        from src.solvers.native_boundary_adapter import identity_digest

        actual = geometry["metadata"]["contract"]
        if identity_digest(actual) != identity_digest(store.expected_contract):
            raise ValueError(
                "physical/basis/geometry/MPC/source consumer contract mismatch"
            )
        native = {k: v for k, v in lit.items() if k != "cell_tags"}
        if (
            actual["native"] != content_hash(native)
            or actual["dependencies"] != store.dependencies
        ):
            raise ValueError("actual saved literal/dependency identity mismatch")
    n = int(geometry["metadata"]["n"])
    nm = int(geometry["metadata"]["ports"])
    V = csr_matrix(
        (sparse["data"], sparse["indices"], sparse["indptr"]),
        shape=tuple(sparse["shape"]),
    )
    if V.shape != (n, n) or not np.isfinite(V.data).all():
        raise ValueError("tiny native oracle shape/finite")
    G = independent_expansion(lit, n)
    C, D = d["C_native"], d["D_native"]
    Ca, Da = d["C_adapter"], d["D_adapter"]
    if (
        C.shape != (n, nm)
        or D.shape != (nm, n)
        or Ca.shape != C.shape
        or Da.shape != D.shape
    ):
        raise ValueError("full port coupling inventory")
    required = {
        "f",
        "g",
        "z",
        "z2",
        "alpha",
        "u",
        "expanded",
        "u2",
        "u_difference",
        "u_zero",
        "reduced_rhs",
        "schur_action",
        "rFE",
        "rport",
        "rnative",
        "native_coupled_u",
        "reduced_injection",
    }
    required.update(
        {
            f"{s}_{k}"
            for s in ("a", "b", "zero", "scale")
            for k in ("x", "volume", "adjoint_volume", "action", "adjoint")
        }
    )
    if not required <= set(d) or any(not np.isfinite(v).all() for v in d.values()):
        raise ValueError("complete finite nonzero recovery inventory")
    if not np.any(d["f"][lit["interiors"]]) or not np.any(d["g"]):
        raise ValueError("nonzero internal and port RHS required")
    for k in ("u", "u2", "u_zero", "u_difference", "f"):
        if np.any(d[k][lit["slaves"]]):
            raise ValueError("independent computation storage slave zero")
    if not len(lit["slaves"]) or not np.any(d["expanded"][lit["slaves"]]):
        raise ValueError("physical expanded periodic witness required")
    checks = []

    def pair(name, left, right):
        checks.append(dict(kind=name, **metric(left, right)))

    pair("complete_B_link", C, Ca)
    pair("complete_normalized_D_link", D, Da)
    pair("expanded_MPC", d["expanded"], G @ d["u"])
    if not np.array_equal(d["scale_x"], (0.37 - 0.91j) * d["a_x"]):
        raise ValueError("complex scale inventory")
    for label in ("a", "b", "zero", "scale"):
        x = d[label + "_x"]
        if x.shape != (n,) or np.any(x[lit["slaves"]]):
            raise ValueError("witness native input inventory")
        pair(label + "_volume", d[label + "_volume"], V @ x)
        pair(
            label + "_adjoint_volume", d[label + "_adjoint_volume"], V.conjugate().T @ x
        )
        pair(label + "_closed_native", d[label + "_action"], V @ x + C @ (D @ x))
        pair(
            label + "_closed_adjoint",
            d[label + "_adjoint"],
            V.conjugate().T @ x + D.conjugate().T @ (C.conjugate().T @ x),
        )
        if label == "zero" and any(
            np.any(d[label + "_" + k])
            for k in ("x", "volume", "adjoint_volume", "action", "adjoint")
        ):
            raise ValueError("strict zero action")
    pair(
        "affine_homogeneous_recovery", d["u"] - d["u2"], d["u_difference"] - d["u_zero"]
    )
    pair("original_augmented_FE", d["rFE"], d["f"] - V @ d["u"] - C @ d["alpha"])
    pair("original_augmented_port", d["rport"], d["g"] + D @ d["u"] - d["alpha"])
    pair(
        "original_native",
        d["rnative"],
        d["f"] - C @ d["g"] - V @ d["u"] - C @ (D @ d["u"]),
    )
    pair(
        "independent_native_augmented_identity", d["rnative"], d["rFE"] - C @ d["rport"]
    )
    pair(
        "physical_callback_recovered_state",
        d["native_coupled_u"],
        V @ d["u"] + C @ (D @ d["u"]),
    )
    active = numbering["owned_active"]
    z = d["z"]
    if not np.array_equal(z[len(active) :], d["alpha"]) or z.shape != (
        len(active) + nm,
    ):
        raise ValueError("trace/port coordinate identity")
    trace_storage = np.zeros(n, np.complex128)
    trace_storage[active] = z[: len(active)]
    local_trace_storage = G @ trace_storage
    expected_reduced = d["f"].copy()
    local_schur_storage = np.zeros(n, np.complex128)
    class_arrays = []
    for item in system["metadata"]["classes"]:
        _row, values = store.read(item["name"])
        class_arrays.append(values)
        ip, tp = values["interior_positions"], values["trace_positions"]
        original = values["original"]
        if original.shape != (882, 882) or len(ip) != 450 or len(tp) != 432:
            raise ValueError("complete p6 native class tensor")
        vii, vit, vti, vtt = (
            original[np.ix_(r, c)] for r, c in ((ip, ip), (ip, tp), (tp, ip), (tp, tp))
        )
        pair(item["name"] + "_recovery_matrix", vii @ values["recovery"], -vit)
        pair(item["name"] + "_rhs_projection", values["rhs_trace"] @ vii, -vti)
        pair(item["name"] + "_Schur", values["schur"], vtt + vti @ values["recovery"])
        lu, piv = values["lu"], values["pivots"]
        L, U = np.tril(lu, -1) + np.eye(len(ip)), np.triu(lu)
        perm = np.arange(len(ip))
        for i, k in enumerate(piv):
            perm[[i, int(k)]] = perm[[int(k), i]]
        pair(item["name"] + "_saved_actual_LU", (L @ U)[np.argsort(perm)], vii)
    for cell, (ii, tt, ci) in enumerate(
        zip(
            numbering["cell_interior"],
            numbering["cell_trace"],
            numbering["cell_class"],
            strict=True,
        )
    ):
        c = class_arrays[int(ci)]
        # Shared trace contributions are assembled first, then norms computed.
        local_load = c["rhs_trace"] @ d["f"][ii]
        raw = np.zeros(n, np.complex128)
        np.add.at(raw, tt, local_load)
        expected_reduced += G.conjugate().T @ raw
        np.add.at(local_schur_storage, tt, c["schur"] @ local_trace_storage[tt])
        ip, tp = c["interior_positions"], c["trace_positions"]
        original = c["original"]
        internal_action = (
            original[np.ix_(ip, ip)] @ d["u"][ii]
            + original[np.ix_(ip, tp)] @ local_trace_storage[tt]
        )
        err = d["f"][ii] - internal_action
        scale = np.linalg.norm(d["f"][ii]) + np.linalg.norm(internal_action)
        # Full operation scale, no amplitude rescaling or dropped native terms.
        checks.append(
            {
                "kind": "cell_internal_rhs_balance",
                "cell": cell,
                "numerator": float(np.linalg.norm(err)),
                "denominator": float(scale),
                "relative": float(np.linalg.norm(err) / scale),
                "worst_row": int(ii[np.argmax(np.abs(err))]),
                "passed": bool(np.linalg.norm(err) <= 1e-10 * scale),
            }
        )
        pair(
            f"cell{cell}_affine_particular",
            original[np.ix_(ip, ip)] @ d["u_zero"][ii],
            d["f"][ii],
        )
    expected_schur = G.conjugate().T @ local_schur_storage + Ca @ d["alpha"]
    pair(
        "independent_compressed_RHS",
        d["reduced_rhs"],
        np.r_[expected_reduced[active], d["g"]],
    )
    pair(
        "independent_condensed_action",
        d["schur_action"],
        np.r_[expected_schur[active], d["alpha"] - Da @ trace_storage],
    )
    pair(
        "original_residual_trace_injection",
        d["reduced_injection"][active],
        d["rFE"][active],
    )
    tags = set(map(int, lit["cell_tags"]))
    if tags != {1, 2} or set(qrow["metadata"]["tags"]) != tags:
        raise ValueError("both physical materials quadrature inventory")
    for tag in sorted(tags):
        required_q = {f"tag{tag}_{k}" for k in ("q15", "q17", "native", "cell")}
        if not required_q <= set(quad):
            raise ValueError("complete original q15/q17 evidence")
        cell, ci = quad[f"tag{tag}_cell"]
        if (
            int(lit["cell_tags"][cell]) != tag
            or int(numbering["cell_class"][cell]) != ci
        ):
            raise ValueError("quadrature geometry/material/class pairing")
        pair(f"tag{tag}_q15_q17", quad[f"tag{tag}_q15"], quad[f"tag{tag}_q17"])
        pair(f"tag{tag}_native_q17", quad[f"tag{tag}_native"], quad[f"tag{tag}_q17"])
        pair(
            f"tag{tag}_class_link",
            quad[f"tag{tag}_native"],
            class_arrays[int(ci)]["original"],
        )
    return {
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "independent_oracle": "unfactored_native_CSR+original_C_D+class_tensors+literal_MPC",
        "native_rows": n,
        "ports": nm,
        "physical_PDE_solved": False,
    }
