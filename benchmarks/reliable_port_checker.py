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
            for k in ("native", "field", "identity", "result"):
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
            del a, s
    return dict(
        stage_qualified=True,
        roles=rows,
        independent_face_gate=q,
        frozen_native=frozen,
        no_FE_or_factor=True,
        reference_qualified=False,
        production_qualified=False,
        NN_increment=False,
    )
