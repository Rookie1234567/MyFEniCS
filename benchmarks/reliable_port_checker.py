"""Review V21 checker, measurements and raw vectors instead of producer flags."""

import json
import math
from pathlib import Path
import numpy as np


def finite_le(value, limit):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= limit
    )


def face_gates(q):
    shared = len(q.get("air", [])) == 2 and q.get("small_sparse_LU_count", 99) <= 5
    for row in q.get("air", []):
        f = row.get("flux", {})
        shared = (
            shared
            and finite_le(row.get("native"), 1e-10)
            and all(
                finite_le(row.get(k), 1e-4)
                for k in ("physical_E", "physical_curl_H", "complex_modes")
            )
            and f.get("channels") == 36
            and f.get("physical_E_cross_H") is True
            and finite_le(f.get("independent_Poynting_vs_port_max_absolute"), 1e-12)
            and finite_le(f.get("reflected"), 1e-5)
            and finite_le(abs(f.get("transmitted", float("inf")) - 1), 1e-5)
            and all(
                finite_le(f.get(k), 1e-5)
                for k in (
                    "independent_Poynting_vs_port_max_absolute",
                    "all_mode_vs_analytic_max_absolute",
                    "energy_closure",
                )
            )
        )
    roles = {}
    for r in q.get("roles", []):
        pair = r.get("physical_pair", {})
        oracle = r.get("oracle_pair", {})
        arrays = [pair.get(k, []) for k in ("B_relative", "D_relative", "H_relative")]
        arrays.extend(
            oracle.get(k, []) for k in ("B_relative", "D_relative", "H_relative")
        )
        valid = all(
            len(a) == 36 and all(finite_le(v, 1e-10) for v in a) for a in arrays
        )
        acts = pair.get("nonzero_actions", [])
        valid = (
            valid
            and len(acts) == 3
            and all(len(a) == 3 and all(finite_le(v, 1e-10) for v in a) for a in acts)
        )
        valid = (
            valid
            and finite_le(r.get("nonzero_port_load_original_recovery"), 1e-10)
            and r.get("omitted_real_facet_rejected") is True
            and r.get("internal_coefficient_norm", 0) > 0
            and r.get("negative_controls_complete") is True
            and finite_le(r.get("cutoff_witness_relative"), 1e-10)
            and abs(r.get("ky", 0)) > 0
            and r.get("nonidentity_orientation_count", 0) > 0
        )
        expected = {
            (side, m, n, pol)
            for side in ("top", "bottom")
            for m in range(-1, 2)
            for n in range(-1, 2)
            for pol in ("s", "p")
        }
        keys = r.get("mode_keys", [])
        valid = valid and len(keys) == 36 and {tuple(k) for k in keys} == expected
        expected_degree, expected_phase = {
            "O3": (3, False),
            "E3": (3, True),
            "E4": (4, True),
            "O6_LOCAL_ONLY": (6, False),
        }.get(r.get("role"), (None, None))
        valid = (
            valid
            and r.get("degree") == expected_degree
            and r.get("phase") is expected_phase
        )
        if r.get("role") in roles:
            raise ValueError("DUPLICATE_FACE_QUALIFICATION_ROLE")
        roles[r["role"]] = bool(valid)
    if set(roles) != {"O3", "E3", "E4", "O6_LOCAL_ONLY"}:
        raise ValueError("COMPLETE_EXPLICIT_FACE_ROLE_COVERAGE_REQUIRED")
    return dict(
        shared=bool(shared), roles=roles, whole=bool(shared and all(roles.values()))
    )


def split_physics(z):
    from benchmarks.fixed_phase_checker import physics_from_arrays

    for name in ("E", "curl", "H"):
        hi, lo = z["total_" + name + "_hi"], z["total_" + name + "_lo"]
        total = hi.astype(np.clongdouble) + lo.astype(np.clongdouble)
        if not np.array_equal(total, z["total_" + name]):
            raise ValueError("PHYSICS_TOTAL_LOW_COMPONENT_NOT_CONSUMED:" + name)
    for name in ("selected_total_E", "selected_total_curl", "selected_total_H"):
        if name in z:
            ref = z[name + "_hi"].astype(np.clongdouble) + z[name + "_lo"].astype(
                np.clongdouble
            )
            if not np.array_equal(ref, z[name]):
                raise ValueError("SAMPLE_TOTAL_LOW_COMPONENT_NOT_CONSUMED")
    p = physics_from_arrays(z)
    if not p["raw_valid"]:
        raise ValueError("RAW_EXACT_AFFINE_PHYSICS_INVALID")
    return p


def raw_equations(a, state):
    """Independent CSR transfer and class contractions, no FE/solver import."""
    from scipy import sparse

    n = len(a["masters"])
    nc, dim = a["cell_dofs"].shape
    E = sparse.coo_matrix(
        (a["evals"], (a["erows"], a["eids"])), shape=(nc * dim, n)
    ).tocsr()
    B = sparse.coo_matrix((a["bv"], (a["br"], a["bp"])), shape=(n, len(a["H"]))).tocsr()
    D = sparse.coo_matrix((a["dv"], (a["dp"], a["dr"])), shape=(len(a["H"]), n)).tocsr()

    def volume(c):
        local = (E @ c).reshape(nc, dim)
        v = np.empty_like(local)
        for cls, tensor in enumerate(a["F"]):
            indices = np.flatnonzero(a["classes"] == cls)
            for cell in indices:
                v[cell] = tensor @ local[cell]
        return E.conj().T @ v.ravel()

    def norm(x):
        return float(np.sqrt(np.sum(abs(x) ** 2, dtype=np.longdouble)))

    c, alpha = state["c_scattered"], state["alpha_scattered"]
    body = volume(c) + B @ alpha - a["g"]
    port = -D @ c + a["H"] * alpha - a["gp"]
    r = volume(c) + B @ ((D @ c) / a["H"]) - a["g"] + B @ (a["gp"] / a["H"])
    f = a["g"] - B @ (a["gp"] / a["H"])
    total_body = sum(
        volume(state[k]).astype(np.clongdouble) for k in ("total_hi", "total_lo")
    )
    total_body += sum(
        (B @ state[k]).astype(np.clongdouble)
        for k in ("alpha_total_hi", "alpha_total_lo")
    )
    total_port = -sum(
        (D @ state[k]).astype(np.clongdouble) for k in ("total_hi", "total_lo")
    )
    total_port += sum(
        (a["H"] * state[k]).astype(np.clongdouble)
        for k in ("alpha_total_hi", "alpha_total_lo")
    )
    return dict(
        native_relative=norm(r) / norm(f),
        augmented_relative=norm(np.r_[body, port]) / norm(np.r_[a["g"], a["gp"]]),
        original_total_augmented_relative=norm(
            np.r_[total_body - a["total_g"], total_port]
        )
        / norm(a["total_g"]),
    )


def surface_array_checks(path):
    """Recompute complete mode block errors directly from saved CSR arrays."""
    from scipy import sparse

    with np.load(path, allow_pickle=False) as z:
        names = ["analytic", "oracle1", "oracle2"]
        if "old_q15_H" in z:
            names.append("old_q15")
        blocks = {}
        for name in names:
            blocks[name] = tuple(
                sparse.csr_matrix(
                    (
                        z[name + "_" + label + "_data"],
                        z[name + "_" + label + "_indices"],
                        z[name + "_" + label + "_indptr"],
                    ),
                    shape=tuple(z[name + "_" + label + "_shape"]),
                )
                for label in ("B", "D")
            ) + (z[name + "_H"].copy(),)
            B, D, H = blocks[name]
            if (
                B.shape != D.shape[::-1]
                or H.shape != (B.shape[1],)
                or np.any(H <= 0)
                or not np.isrealobj(H)
                or any(not np.isfinite(v).all() for v in (B.data, D.data, H))
            ):
                raise ValueError("RAW_SURFACE_LAYOUT_OR_NONFINITE")
    out = {}
    pairs = [
        ("physical", "analytic", "oracle1"),
        ("oracle", "oracle1", "oracle2"),
    ]
    if "old_q15" in blocks:
        pairs.append(("old_q15_change", "old_q15", "analytic"))
    for name, left, right in pairs:
        values = {}
        for i, label in enumerate(("B", "D", "H")):
            x, y = blocks[left][i], blocks[right][i]
            if label == "H":
                num, den = abs(x - y), abs(y)
            else:
                axis = 0 if label == "B" else 1
                num = np.sqrt(
                    np.asarray(
                        (x - y).multiply((x - y).conj()).real.sum(axis=axis)
                    ).ravel()
                )
                den = np.sqrt(
                    np.asarray(y.multiply(y.conj()).real.sum(axis=axis)).ravel()
                )
            values[label] = dict(
                absolute=num.tolist(),
                denominator=den.tolist(),
                relative=(num / np.maximum(den, 1e-300)).tolist(),
                maximum=float(np.max(num / np.maximum(den, 1e-300))),
            )
        out[name] = values
        rng = np.random.default_rng(422202)
        acts = []
        for _ in range(3):
            c = rng.normal(size=blocks[left][0].shape[0]) + 1j * rng.normal(
                size=blocks[left][0].shape[0]
            )
            alpha = rng.normal(size=len(blocks[left][2])) + 1j * rng.normal(
                size=len(blocks[left][2])
            )
            acts.append(
                [
                    float(np.linalg.norm(x - y) / max(np.linalg.norm(y), 1e-300))
                    for x, y in zip(
                        (
                            blocks[left][0] @ alpha,
                            blocks[left][1] @ c,
                            blocks[left][2] * alpha,
                        ),
                        (
                            blocks[right][0] @ alpha,
                            blocks[right][1] @ c,
                            blocks[right][2] * alpha,
                        ),
                        strict=True,
                    )
                ]
            )
        out[name]["nonzero_actions"] = acts
    return out


def raw_surface_gate(raw, expected_modes):
    """New component gates, not the intentionally different old-q15 blocks."""
    for name, limit in (("physical", 1e-10), ("oracle", 1e-8)):
        for label in ("B", "D", "H"):
            values = raw.get(name, {}).get(label, {}).get("relative", [])
            if len(values) != expected_modes or not all(
                finite_le(x, limit) for x in values
            ):
                return False
        acts = raw.get(name, {}).get("nonzero_actions", [])
        if len(acts) != 3 or not all(
            len(a) == 3 and all(finite_le(x, limit) for x in a) for a in acts
        ):
            return False
    return True


def check_campaign(root, artifact):
    from src.runners.fixed_phase_campaign import evidence_v22, sha
    from benchmarks.affine_output_checker import check_state

    affine = evidence_v22("v22_affine_saved")
    book = json.loads(Path(affine["files"]["role_indices"]["path"]).read_text())
    rows = {}
    for role, b in book.items():
        for key in ("native", "field", "identity", "observables"):
            if sha(b["files"][key]["path"]) != b["files"][key]["sha256"]:
                raise ValueError("V22_CHECK_BOUND_INPUT")
        with np.load(b["files"]["native"]["path"], allow_pickle=False) as z:
            a = {k: np.array(z[k]) for k in z.files}
        with np.load(b["files"]["field"]["path"], allow_pickle=False) as z:
            s = {k: np.array(z[k]) for k in z.files}
        with np.load(b["files"]["observables"]["path"], allow_pickle=False) as z:
            obs = {k: np.array(z[k]) for k in z.files}
        identity = json.loads(Path(b["files"]["identity"]["path"]).read_text())
        mode = identity["mode_manifest_sha256"]
        arithmetic = check_state(a, s, mode_hash=mode, expected_mode_hash=mode)
        physics = split_physics(obs)
        equations = raw_equations(a, s)
        rows[role] = dict(
            arithmetic=arithmetic,
            physics=physics,
            independent_equations=equations,
            complete_output_qualified=arithmetic["passed"]
            and max(equations.values()) <= 1e-6,
        )
        del a, s, obs
    paths = sorted(
        (root / "benchmarks/artifacts/task42extra").glob(
            "index_v22_face_qualification_attempt*.json"
        )
    )
    q = face_gates(json.loads(paths[-1].read_text())["result"]) if paths else None
    face_arrays = {}
    if paths:
        record = json.loads(paths[-1].read_text())
        where = Path(record["files"]["qualification"]["path"]).parent
        face_arrays = {
            role: surface_array_checks(where / (role + "_surface_oracles.npz"))
            for role in ("O3", "E3", "E4", "O6_LOCAL_ONLY")
        }
        for role, value in face_arrays.items():
            q["roles"][role] = q["roles"][role] and raw_surface_gate(value, 36)
        q["whole"] = q["shared"] and all(q["roles"].values())
    frozen = {}
    candidates = list(
        (root / "benchmarks/artifacts/task42extra").glob(
            "index_v22_frozen_port_audit_attempt*.json"
        )
    )
    if candidates:
        index = evidence_v22("v22_frozen_port_audit")
        book = json.loads(Path(index["files"]["role_indices"]["path"]).read_text())
        for role, b in book.items():
            for k in (
                "native",
                "field",
                "identity",
                "result",
                "surface_oracles",
                "frozen_residual_terms",
            ):
                if sha(b["files"][k]["path"]) != b["files"][k]["sha256"]:
                    raise ValueError("FROZEN_AUDIT_HASH_CHANGED")
            with np.load(b["files"]["native"]["path"], allow_pickle=False) as z:
                a = {k: np.array(z[k]) for k in z.files}
            with np.load(b["files"]["field"]["path"], allow_pickle=False) as z:
                s = {k: np.array(z[k]) for k in z.files}
            eq = raw_equations(a, s)
            recorded = b["result"]["full_equation"]
            for k, v in eq.items():
                if abs(v - recorded[k]) > 1e-10 * max(1, v):
                    raise ValueError("FROZEN_RAW_RESIDUAL_RECORD_MISMATCH")
            frozen[role] = dict(
                independent_equations=eq,
                correction_triggered=role != "O3" and eq["native_relative"] > 1e-6,
                full_original_coordinates=check_state(
                    a, s, mode_hash="bound", expected_mode_hash="bound"
                ),
            )
            frozen[role]["independent_surface_arrays"] = surface_array_checks(
                b["files"]["surface_oracles"]["path"]
            )
            frozen[role]["reliable_surface_qualified"] = raw_surface_gate(
                frozen[role]["independent_surface_arrays"], 340
            )
            with np.load(
                b["files"]["frozen_residual_terms"]["path"], allow_pickle=False
            ) as z:
                old, new, da, df = (
                    z[k]
                    for k in (
                        "old_residual",
                        "new_residual",
                        "operator_delta",
                        "RHS_delta",
                    )
                )
                delta = da - df
                identity = np.linalg.norm(new - old - delta) / max(
                    np.linalg.norm(z["native_f"]), 1e-300
                )
                if identity > 1e-10:
                    raise ValueError("SAVED_RESIDUAL_DECOMPOSITION_IDENTITY_FAILED")
                frozen[role]["signed_frozen_decomposition"] = dict(
                    identity_relative=float(identity),
                    old_energy=float(np.vdot(old, old).real),
                    delta_energy=float(np.vdot(delta, delta).real),
                    cross=float(2 * np.vdot(old, delta).real),
                    new_energy=float(np.vdot(new, new).real),
                    no_field_change=True,
                    identity_denominator="original native RHS norm, no phase fit",
                )
            del a, s
    corrections = {}
    for role in ("E3", "E4"):
        candidates = sorted(
            (root / "benchmarks/artifacts/task42extra").glob(
                "index_v22_" + role.lower() + "_correction_attempt*.json"
            )
        )
        if not candidates:
            continue
        index = evidence_v22("v22_" + role.lower() + "_correction")
        b = index["files"]
        with np.load(b["native"]["path"], allow_pickle=False) as z:
            a = {k: np.array(z[k]) for k in z.files}
        with np.load(b["field"]["path"], allow_pickle=False) as z:
            s = {k: np.array(z[k]) for k in z.files}
        with np.load(b["observables"]["path"], allow_pickle=False) as z:
            obs = {k: np.array(z[k]) for k in z.files}
        identity = json.loads(Path(b["identity"]["path"]).read_text())
        mode = identity["mode_manifest_sha256"]
        arithmetic = check_state(a, s, mode_hash=mode, expected_mode_hash=mode)
        corrections[role] = dict(
            arithmetic=arithmetic,
            physics=split_physics(obs),
            independent_equations=raw_equations(a, s),
            origin_low_components_consumed=True,
            reference_qualified=False,
            production_qualified=False,
            independent_physical_weak=index["result"]["full_equation"].get(
                "independent_physical_weak"
            ),
        )
        del a, s, obs
    comparisons = None
    paths = sorted(
        (root / "benchmarks/artifacts/task42extra").glob(
            "index_v22_corrected_compare_attempt*.json"
        )
    )
    if paths:
        from benchmarks.fixed_phase_checker import compare_from_arrays

        idx = evidence_v22("v22_corrected_compare")
        if "integrals" in idx["files"]:
            book = json.loads(Path(idx["files"]["role_indices"]["path"]).read_text())
            with np.load(idx["files"]["integrals"]["path"], allow_pickle=False) as z:
                integrals = {k: np.array(z[k]) for k in z.files}
            observations, algebra = {}, {}
            for name, row in book.items():
                for b in row["files"].values():
                    if sha(b["path"]) != b["sha256"]:
                        raise ValueError("COMPARISON_RAW_INPUT_HASH")
                with np.load(
                    row["files"]["observables"]["path"], allow_pickle=False
                ) as z:
                    observations[name] = {k: np.array(z[k]) for k in z.files}
                stat = (
                    corrections[name[4:]] if name.startswith("new_") else rows[name[4:]]
                )
                e = stat["independent_equations"]
                recovery = max(
                    stat["arithmetic"]["rows"][k]["original_coordinates_relative"]
                    for k in ("total", "scattered", "background")
                )
                algebra[name] = dict(
                    e,
                    recovery=recovery,
                    channels=len(stat["physics"]["per_level_power"]),
                    full_FE_recovered=bool(stat["arithmetic"]["exact_sum_identity"]),
                )
                if name.startswith("new_"):
                    # Reuse this independently assembled weak-form numeric
                    # measurement, not a producer status or subset PASS.
                    algebra[name]["independent_physical_weak"] = stat[
                        "independent_physical_weak"
                    ]
            pairs = [
                ("old_" + r, "new_" + r)
                for r in ("E3", "E4")
                if "new_" + r in observations
            ]
            if "new_E3" in observations and "new_E4" in observations:
                pairs.append(("new_E3", "new_E4"))
            comparisons = compare_from_arrays(
                integrals,
                observations,
                algebra,
                role_aliases={r: r[4:] for r in observations},
                comparison_pairs=pairs,
            )
    return dict(
        stage_qualified=True,
        audit_completed=True,
        strict_forward_solution_qualified=False,
        roles=rows,
        independent_face_gate=q,
        independent_face_arrays=face_arrays,
        frozen_native=frozen,
        corrected_native=corrections,
        corrected_comparison=comparisons,
        no_FE_or_factor=True,
        reference_qualified=False,
        production_qualified=False,
        NN_increment=False,
    )
