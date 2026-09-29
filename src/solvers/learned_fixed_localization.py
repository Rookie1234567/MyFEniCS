"""Finite diagnostics of frozen B/C/B2; never an iterative solver or fallback.

All long arrays are vectors or rank-bounded bases.  The supplied two-level PC
and its original operator are borrowed, and no checkpoint is modified.
"""

import numpy as np
from scipy.linalg import blas, qr, svd, svdvals

RANK_TOL = 1.0e-10
CHECK_TOL = 1.0e-10
CAP = 512 * 2**20


def norm(value):
    return float(np.linalg.norm(value))


def relative(value, scale):
    return float(value / scale) if scale else float(value)


def complex_pair(value):
    return [float(np.real(value)), float(np.imag(value))]


def defect(left, right, *scales):
    return relative(norm(left - right), norm(left) + norm(right) + sum(scales))


def diagnostic_budget(rows, rank, full_rows, local_representation, local_factors):
    if not 0 < rank <= 128 or rank >= rows:
        raise ValueError("fixed bounded rank required")
    # These envelopes include archive extraction/copies and LAPACK workspace.
    # Stream one state/correction at a time; no n x 129 ZB matrix is allocated.
    items = {
        "owned_Z_U": 2 * rows * rank * 16,
        "archive_extraction_reserve": 2 * rows * rank * 16,
        "diagnostic_PC_vectors_and_two_column_LS": 80 * rows * 16,
        "probe_input_output_QR_SVD_workspace": 8 * rows * 16 * 16,
        "original_audit_full_vectors": 40 * full_rows * 16,
        "small_129_column_LAPACK_and_R": 12 * (rank + 1) ** 2 * 16,
        "streamed_RHS_state_and_residual": (6 * rows + 3 * full_rows) * 16,
        "geometry_indices_weights_buffers": local_representation,
    }
    representation = sum(items.values())
    factors = local_factors + rank * rank * 16
    if representation > CAP or factors > CAP:
        raise ValueError("V5 preconstruction diagnostic capacity exceeded")
    return {
        "allocation_envelopes_bytes": items,
        "representation_workspace_bound_bytes": representation,
        "all_factor_bound_bytes": factors,
        "representation_cap_bytes": CAP,
        "factor_cap_bytes": CAP,
        "ZB_LS_storage": "compressed <=129x129; no second tall n x129 array",
        "probe_max_columns": 16,
        "common_state_streamed": True,
        "private_audit_CSR": False,
    }


def projection(basis, vector):
    return blas.zgemv(1.0, basis, vector, trans=2)


def coverage(vector, basis):
    length = norm(vector)
    coefficients = projection(basis, vector)
    represented = basis @ coefficients
    remaining = vector - represented
    if not length:
        return (
            {
                "vector_norm": 0.0,
                "represented_norm": 0.0,
                "outside_norm": 0.0,
                "eta": 0.0,
                "gamma": 0.0,
                "pythagoras_defect": 0.0,
                "zero_rule": "exact zero; coverage fractions not applicable",
            },
            represented,
            remaining,
        )
    eta, gamma = norm(remaining) / length, norm(coefficients) / length
    result = {
        "vector_norm": length,
        "represented_norm": norm(represented),
        "outside_norm": norm(remaining),
        "eta": eta,
        "gamma": gamma,
        "pythagoras_defect": abs(eta**2 + gamma**2 - 1.0),
        "zero_rule": "nonzero relative norm",
    }
    if result["pythagoras_defect"] > CHECK_TOL:
        raise ValueError("coverage orthogonal-decomposition identity failed")
    return result, represented, remaining


def scaled_thin_lstsq(matrix, rhs):
    """Diagnostic minimum norm after explicit unit-column scaling, thin SVD.

    The physical search space is unchanged.  Rank threshold is fixed at 1e-10;
    zero columns are excluded deterministically, never replaced or regularized.
    """
    if matrix.ndim != 2 or matrix.shape[1] > 129:
        raise ValueError("diagnostic LS limited to 129 columns")
    scales = np.linalg.norm(matrix, axis=0)
    keep = scales > 0.0
    coefficients = np.zeros(matrix.shape[1], dtype=np.complex128)
    if not np.any(keep):
        return coefficients, {
            "effective_rank": 0,
            "column_scales": scales.tolist(),
            "singular_values": [],
            "rank_relative_threshold": RANK_TOL,
            "zero_columns": np.flatnonzero(~keep).tolist(),
            "column_scaling": "unit nonzero image norm; coefficients unscaled back",
        }
    normalized = np.asfortranarray(matrix[:, keep] / scales[keep])
    left, values, vh = svd(
        normalized, full_matrices=False, lapack_driver="gesdd", check_finite=False
    )
    rank = int(np.count_nonzero(values > RANK_TOL * values[0]))
    projected = projection(np.asfortranarray(left[:, :rank]), rhs)
    solved = vh[:rank].conj().T @ (projected / values[:rank])
    coefficients[keep] = solved / scales[keep]
    if not np.isfinite(coefficients).all():
        raise ValueError("diagnostic LS nonfinite")
    return coefficients, {
        "effective_rank": rank,
        "column_scales": scales.tolist(),
        "singular_values": values.tolist(),
        "rank_relative_threshold": RANK_TOL,
        "zero_columns": np.flatnonzero(~keep).tolist(),
        "column_scaling": "unit nonzero image norm; coefficients unscaled back",
    }


def direction_metrics(residual, correction, image, image_reference):
    rn, dn, yn = norm(residual), norm(correction), norm(image)
    inner = np.vdot(image, residual)
    cutoff = RANK_TOL * image_reference
    skipped = not yn or yn <= cutoff
    # Normalize before computing the step to avoid squared-norm underflow.
    alpha = 0j if skipped else np.vdot(image / yn, residual) / yn
    opt = residual - alpha * image
    result = {
        "residual_norm": rn,
        "correction_norm": dn,
        "S_image_norm": yn,
        "image_inner_residual": complex_pair(inner),
        "rho_unit": relative(norm(residual - image), rn),
        "rho_opt": relative(norm(opt), rn),
        "alpha": complex_pair(alpha),
        "image_skip_scale": image_reference,
        "image_skip_cutoff": cutoff,
        "optimal_scalar_skipped": skipped,
        "skip_reason": "zero/numerically tiny image at fixed relative1e-10"
        if skipped
        else None,
        "zero_residual_rule": "absolute remaining norm" if not rn else None,
    }
    if not np.isfinite(alpha):
        raise ValueError("nonfinite diagnostic complex scalar")
    return result, alpha * correction


def image_angles(images):
    result = []
    for i, first in enumerate(images):
        for j in range(i + 1, len(images)):
            second = images[j]
            scale = norm(first) * norm(second)
            cosine = np.vdot(first, second) / scale if scale else 0j
            result.append(
                {
                    "terms": [i, j],
                    "Hermitian_cosine": complex_pair(cosine),
                    "absolute_cosine": float(abs(cosine)),
                    "real_cosine": float(np.real(cosine)),
                    "zero_term": not scale,
                }
            )
    return result


def same_residual_actions(pc, residual):
    """Same r for B/C/B2, decompositions and two finite search counterfactuals."""
    original = residual.copy()
    cr = pc.coarse_array(residual)
    br = pc.local.apply_array(residual)
    b2r = pc.apply_array(residual)
    images = {name: pc.operator(d) for name, d in (("B", br), ("C", cr), ("B2", b2r))}
    coverage_r, pi, er = coverage(residual, pc.u)
    bpi = pc.local.apply_array(pi)
    ber = pc.local.apply_array(er)
    h_er = pc.operator(ber)
    csber = pc.coarse_array(h_er)
    terms = (cr, -bpi, -csber)
    term_images = (images["C"], -pc.operator(bpi), -pc.operator(csber))
    sb2_expected = pi + h_er - pc.u @ projection(pc.u, h_er)
    identities = {
        "SB2_vs_Pi_plus_EHE": defect(images["B2"], sb2_expected, norm(pi), norm(h_er)),
        "B2_minus_B_three_terms": defect(b2r - br, sum(terms), norm(b2r), norm(br)),
        "S_three_terms": defect(images["B2"] - images["B"], sum(term_images)),
        "r_minus_SCr_vs_Er": defect(residual - images["C"], er, norm(residual)),
    }
    if max(identities.values()) > CHECK_TOL:
        raise ValueError("frozen B2 additional identity failed")
    reference = max(norm(residual), *(norm(a) for a in images.values()))
    directions, corrections = {}, {}
    for name, d in (("B", br), ("C", cr), ("B2", b2r)):
        directions[name], optimum = direction_metrics(
            residual, d, images[name], reference
        )
        corrections[name + "_unit"] = d
        corrections[name + "_opt"] = optimum

    coeff_bc, ls_bc = scaled_thin_lstsq(
        np.column_stack((images["B"], images["C"])), residual
    )
    corrections["BC_LS"] = coeff_bc[0] * br + coeff_bc[1] * cr

    # Orthonormal coordinate compression of [SZ, SB] = [UR, U h + t].
    h = projection(pc.u, images["B"])
    t = images["B"] - pc.u @ h
    tn = norm(t)
    rank = pc.rank
    small = np.zeros((rank + 1, rank + 1), dtype=np.complex128, order="F")
    small[:rank, :rank] = pc.r
    small[:rank, rank] = h
    small[rank, rank] = tn
    small_rhs = np.empty(rank + 1, dtype=np.complex128)
    small_rhs[:rank] = projection(pc.u, residual)
    small_rhs[rank] = np.vdot(t / tn, residual) if tn else 0j
    coeff_zb, ls_zb = scaled_thin_lstsq(small, small_rhs)
    corrections["ZB_LS"] = pc.z @ coeff_zb[:rank] + coeff_zb[rank] * br
    rho_bc = relative(
        norm(residual - pc.operator(corrections["BC_LS"])), norm(residual)
    )
    rho_zb = relative(
        norm(residual - pc.operator(corrections["ZB_LS"])), norm(residual)
    )
    if (
        norm(residual)
        and max(
            rho_zb - rho_bc,
            rho_bc - directions["B"]["rho_opt"],
            rho_zb - coverage_r["eta"],
        )
        > CHECK_TOL
    ):
        raise ValueError(
            "diagnostic search-space inclusion failed at fixed rank tolerance"
        )
    if not np.array_equal(original, residual):
        raise ValueError("diagnostic residual input was modified")
    result = {
        "coverage_r": coverage_r,
        "additional_identities": identities,
        "directions": directions,
        "difference_terms": [
            {"name": name, "norm": norm(d), "S_image_norm": norm(y)}
            for name, d, y in zip(
                ("Cr", "-B_Pi_r", "-C_S_B_Er"), terms, term_images, strict=True
            )
        ],
        "S_term_angles": image_angles(term_images),
        "S_term_cancellation_ratio": relative(
            norm(sum(term_images)), sum(norm(y) for y in term_images)
        ),
        "rho_BC": rho_bc,
        "rho_ZB": rho_zb,
        "LS_BC": {**ls_bc, "coefficients": [complex_pair(c) for c in coeff_bc]},
        "LS_ZB": {**ls_zb, "coefficients": [complex_pair(c) for c in coeff_zb]},
        "ZB_compression_t_norm": tn,
        "ZB_compression_UH_t_relative": relative(
            norm(projection(pc.u, t)), norm(images["B"])
        ),
        "diagnostic_only": True,
    }
    arrays = {
        "r": original,
        "Pi_r": pi,
        "E_r": er,
        **{"d_" + name: d for name, d in corrections.items()},
        **{"S_" + name: y for name, y in images.items()},
        **{"term_" + str(i): a for i, a in enumerate(terms)},
        **{"S_term_" + str(i): a for i, a in enumerate(term_images)},
    }
    return result, corrections, arrays


def complement_probes(pc, residuals, *, seed=420805):
    """At most twelve fixed residuals plus four fixed random complement inputs."""
    if len(residuals) > 12:
        raise ValueError("at most twelve common residual directions")
    rng = np.random.default_rng(seed)
    candidates = list(residuals) + [
        (
            f"random_seed{seed}_{j}",
            rng.standard_normal(pc.rows) + 1j * rng.standard_normal(pc.rows),
        )
        for j in range(4)
    ]
    accepted, sources = [], []
    for label, candidate in candidates:
        cn = norm(candidate)
        v = candidate - pc.u @ projection(pc.u, candidate)
        vn = norm(v)
        if not cn or vn <= RANK_TOL * cn:
            sources.append(
                {
                    "source": label,
                    "kept": False,
                    "reason": "zero/tiny E input",
                    "input_norm": cn,
                    "E_norm": vn,
                }
            )
            continue
        v /= vn
        for _ in range(2):
            for previous in accepted:
                v -= previous * np.vdot(previous, v)
        remaining = norm(v)
        keep = remaining > RANK_TOL
        sources.append(
            {
                "source": label,
                "kept": keep,
                "input_norm": cn,
                "E_norm": vn,
                "independent_norm": remaining,
                "reason": None if keep else "dependent at fixed relative1e-10",
            }
        )
        if keep:
            accepted.append(v / remaining)
    if not accepted:
        return {"status": "NO_VALID_COMPLEMENT_PROBE", "sources": sources}, {}
    v, _ = qr(np.column_stack(accepted), mode="economic", check_finite=False)
    v = np.asfortranarray(v)
    rank = v.shape[1]
    gram = blas.zgemm(1.0, v, v, trans_a=2)
    uhv = blas.zgemm(1.0, pc.u, v, trans_a=2)
    orth = norm(gram - np.eye(rank)) / np.sqrt(rank)
    complement = norm(uhv) / np.sqrt(rank)
    if max(orth, complement) > CHECK_TOL:
        raise ValueError("probe basis not in the orthonormal U complement")
    y = np.empty_like(v, order="F")
    for j in range(rank):
        y[:, j] = pc.operator(pc.local.apply_array(v[:, j]))
    components = blas.zgemm(1.0, pc.u, y, trans_a=2)
    parallel = pc.u @ components
    perpendicular = y - parallel
    left, values, vh = svd(perpendicular, full_matrices=False, check_finite=False)
    del left
    small = blas.zgemm(1.0, v, np.asfortranarray(perpendicular), trans_a=2)
    witness_coefficients = vh[-1].conj()
    witness = v @ witness_coefficients
    hv = pc.operator(pc.local.apply_array(witness))
    pi_hv = pc.u @ projection(pc.u, hv)
    tv = hv - pi_hv
    checks = []
    for j in range(rank):
        sb2v = pc.operator(pc.apply_array(v[:, j]))
        checks.append(defect(sb2v, perpendicular[:, j], norm(y[:, j])))
    sb2_witness = pc.operator(pc.apply_array(witness))
    checks.append(defect(sb2_witness, tv, norm(hv)))
    checks.extend(
        (
            defect(hv, y @ witness_coefficients),
            defect(tv, perpendicular @ witness_coefficients, norm(hv)),
        )
    )
    decomposition = relative(
        abs(norm(y) ** 2 - norm(parallel) ** 2 - norm(perpendicular) ** 2), norm(y) ** 2
    )
    if max(*checks, decomposition) > CHECK_TOL:
        raise ValueError("true complement/B2 or complete-image decomposition failed")
    result = {
        "status": "BOUNDED_COMPLEMENT_AUDIT_COMPLETE",
        "seed": seed,
        "registered_probe_count": len(candidates),
        "effective_rank": rank,
        "sources": sources,
        "V_orthogonality": orth,
        "UH_V_relative": complement,
        "HV_norm": norm(y),
        "TV_norm": norm(perpendicular),
        "Pi_HV_norm": norm(parallel),
        "HV_singular_values": svdvals(y, check_finite=False).tolist(),
        "TV_singular_values": values.tolist(),
        "Pi_HV_singular_values": svdvals(parallel, check_finite=False).tolist(),
        "small_VH_TV_singular_values": svdvals(small, check_finite=False).tolist(),
        "orthogonal_image_decomposition_defect": decomposition,
        "witness": {
            "v_norm": norm(witness),
            "HV_absolute": norm(hv),
            "TV_absolute": norm(tv),
            "Pi_HV_absolute": norm(pi_hv),
            "TV_over_HV": relative(norm(tv), norm(hv)),
            "TV_over_largest_sampled_HV_singular": relative(
                norm(tv), svdvals(y, check_finite=False)[0]
            ),
            "Hv_over_largest_sampled_HV_singular": relative(
                norm(hv), svdvals(y, check_finite=False)[0]
            ),
            "right_coefficients": [complex_pair(c) for c in witness_coefficients],
        },
        "real_SB2_vs_TV_max_defect": max(checks),
        "interpretation_limit": "sampled U-complement only; no global singularity/condition number claim",
    }
    return result, {
        "V": v,
        "HV": y,
        "TV": perpendicular,
        "Pi_HV": parallel,
        "small_VH_TV": small,
        "w": witness_coefficients,
        "v": witness,
        "Hv": hv,
        "Tv": tv,
        "Pi_Hv": pi_hv,
        "SB2v": sb2_witness,
    }
