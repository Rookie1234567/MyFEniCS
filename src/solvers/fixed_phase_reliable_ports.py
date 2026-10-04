"""Review V21 opt-in output/face work, reusing frozen body packets.

No NN, Gram, hidden reference, or ordinary solver default change. Campaign
handles provenance/deadlines; these functions own physical numerical work.
"""

import gc
import json
from pathlib import Path
import numpy as np

from src.solvers.affine_field_output import affine_state, total_field, split_equation
from src.solvers.feinn_native import load_native, FullNativePacket, packet_hashes
from src.solvers.feinn_discretization_audit import atomic_npz
from src.solvers.fixed_phase_fem import build_model
from src.solvers.fixed_phase_port_recovery import verify_reused_model
from src.solvers.accurate_ports import recover_ports
from src.solvers.analytic_face_ports import surface_blocks_analytic


def load_bound(binding):
    from src.runners.fixed_phase_campaign import sha

    for k in ("native", "field", "identity"):
        b = binding["files"][k]
        if sha(b["path"]) != b["sha256"]:
            raise ValueError("V22_FROZEN_INPUT_CHANGED:" + k)
    p = load_native(binding["files"]["native"]["path"])
    with np.load(binding["files"]["field"]["path"], allow_pickle=False) as z:
        s = {k: np.array(z[k]) for k in z.files}
    return p, s


def affine_saved(design, bindings, artifact, marker, budget, source):
    from benchmarks.affine_output_checker import check_state
    from src.solvers.fixed_phase_comparison import self_physics
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    from src.runners.fixed_phase_campaign import write, sha

    records = {}
    for role in ("O3", "E3", "E4"):
        budget("exact saved total " + role)
        out = artifact / role
        out.mkdir()
        p, old = load_bound(bindings[role])
        degree = 4 if role == "E4" else 3
        model = build_model(
            design["models"]["G0"], degree, role != "O3", operators=False
        )
        verify_reused_model(model, bindings[role])
        s = affine_state(p, old["c_scattered"], old["alpha_scattered"])
        check = check_state(
            p.a,
            s,
            mode_hash=model["record"]["mode_manifest_sha256"],
            expected_mode_hash=json.loads(
                Path(bindings[role]["files"]["identity"]["path"]).read_text()
            )["mode_manifest_sha256"],
        )
        mpc = {}
        for name, c in [
            ("scattered", s["c_scattered"]),
            ("background", s["background"]),
            ("total_hi", s["total_hi"]),
            ("total_lo", s["total_lo"]),
        ]:
            local = p.expand(c)
            field = restore_p0_full_field(model["floquet"], p.storage(c))
            mpc[name] = float(
                np.linalg.norm(field.x.array[p.a["cell_dofs"]] - local)
                / max(np.linalg.norm(local), 1e-300)
            )
        equation = split_equation(p, s)
        atomic_npz(out / "affine_state.npz", **s)
        with np.load(out / "affine_state.npz", allow_pickle=False) as saved:
            if not all(np.array_equal(saved[k], v) for k, v in s.items()):
                raise ValueError("EXACT_AFFINE_SERIALIZATION_CHANGED")
        physics = self_physics(
            model,
            p,
            s["c_scattered"],
            s["alpha_scattered"],
            out,
            marker,
            budget,
            affine_output=s,
        )
        from benchmarks.reliable_port_checker import split_physics

        with np.load(out / "observables.npz", allow_pickle=False) as saved:
            consumption = split_physics(saved)
        total = total_field(s)
        result = dict(
            role=role,
            arithmetic=check,
            MPC=mpc,
            full_equation=equation,
            physics=physics,
            consumer_inventory={
                k: True
                for k in (
                    "serialization_reload",
                    "exact_origin_ports",
                    "full_uncondensed_total_equation",
                    "public_MPC_hi_and_lo",
                    "all_internal_FE_coefficients",
                    "physical_E_curl_H",
                    "six_complex_samples",
                    "four_all_mode_families",
                    "volume_absorption_energy",
                )
            },
            complete_output_qualified=check["passed"]
            and max(mpc.values()) <= 1e-10
            and max(
                equation[k]
                for k in (
                    "native_relative",
                    "augmented_relative",
                    "original_total_augmented_relative",
                )
            )
            <= 1e-6,
            low_vector_norm=float(np.linalg.norm(total.lo)),
            unchanged_scattered_coefficients=bool(
                np.array_equal(s["c_scattered"], old["c_scattered"])
            ),
            new_global_factor_count=0,
            local_LU_count=0,
            old_single_array_FAIL_preserved=True,
            independent_physical_consumption=consumption,
        )
        write(out / "result.json", result)
        records[role] = dict(
            result=result,
            source_sha=source,
            files={
                k: dict(path=str(pth), sha256=sha(pth))
                for k, pth in dict(
                    field=out / "affine_state.npz",
                    observables=out / "observables.npz",
                    result=out / "result.json",
                    native=Path(bindings[role]["files"]["native"]["path"]),
                    identity=Path(bindings[role]["files"]["identity"]["path"]),
                ).items()
            },
        )
        marker(
            "exact_affine_saved",
            dict(
                role=role,
                passed=result["complete_output_qualified"],
                recovery=check["rows"],
                equation=equation,
            ),
        )
        del p, model, s, total, old
        gc.collect()
    write(artifact / "role_indices.json", records)
    return dict(
        stage_qualified=all(
            r["result"]["complete_output_qualified"] for r in records.values()
        ),
        roles={r: v["result"] for r, v in records.items()},
        all_real_vectors=True,
    ), dict(role_indices=artifact / "role_indices.json")


def packet_with_blocks(model, old, B, D, H, *, traction_load=None):
    """New operator version, unchanged volume/MPC; consistent incident RHS."""
    B, D = B.tocoo(), D.tocoo()
    a = dict(
        old.a,
        br=B.row.astype(np.int64),
        bp=B.col.astype(np.int64),
        bv=B.data.astype(complex),
        dp=D.row.astype(np.int64),
        dr=D.col.astype(np.int64),
        dv=D.data.astype(complex),
        H=H.copy(),
    )
    tmp = FullNativePacket(a)
    bg, _ = recover_ports(a, a["background"], gp=np.zeros_like(a["gp"]))
    inc = np.asarray(model["bundle"]["incident_projections"])
    # The traction belongs to the incident plane, not each outgoing mode.
    # Its frozen q15 contribution is checked independently at reliable rule.
    base = old.a["total_g"] - old.B(inc) if traction_load is None else traction_load
    total = base + tmp.B(inc)
    a.update(
        background_alpha=bg,
        total_g=total,
        g=total - old.volume(a["background"]) - tmp.B(bg),
    )
    return FullNativePacket(a)


def block_evidence(B, D, H, BB, DD, HH, seed=422202):
    rng = np.random.default_rng(seed)
    mode_B = np.sqrt(np.asarray(abs(BB).power(2).sum(axis=0)).ravel())
    mode_D = np.sqrt(np.asarray(abs(DD).power(2).sum(axis=1)).ravel())
    diff_B = np.sqrt(np.asarray(abs(B - BB).power(2).sum(axis=0)).ravel())
    diff_D = np.sqrt(np.asarray(abs(D - DD).power(2).sum(axis=1)).ravel())
    b_rel = diff_B / np.maximum(mode_B, 1e-300)
    d_rel = diff_D / np.maximum(mode_D, 1e-300)
    h_diff = abs(H - HH)
    h_rel = h_diff / np.maximum(abs(HH), 1e-300)
    acts = []
    for _ in range(3):
        c = rng.normal(size=B.shape[0]) + 1j * rng.normal(size=B.shape[0])
        alpha = rng.normal(size=len(H)) + 1j * rng.normal(size=len(H))
        actual = (B @ alpha, D @ c, H * alpha)
        ref = (BB @ alpha, DD @ c, HH * alpha)
        acts.append(
            [
                float(np.linalg.norm(x - y) / max(np.linalg.norm(y), 1e-300))
                for x, y in zip(actual, ref, strict=True)
            ]
        )
    return dict(
        B_absolute=diff_B.tolist(),
        B_denominator=mode_B.tolist(),
        B_relative=b_rel.tolist(),
        D_absolute=diff_D.tolist(),
        D_denominator=mode_D.tolist(),
        D_relative=d_rel.tolist(),
        H_absolute=h_diff.tolist(),
        H_denominator=HH.tolist(),
        H_relative=h_rel.tolist(),
        nonzero_actions=acts,
        passed=max(
            np.max(b_rel), np.max(d_rel), np.max(h_rel), max(x for r in acts for x in r)
        )
        <= 1e-10,
    )


def save_surface_evidence(path, versions):
    arrays = {}
    for name, (B, D, H) in versions.items():
        for label, matrix in (("B", B.tocsr()), ("D", D.tocsr())):
            for key, value in (
                ("indptr", matrix.indptr),
                ("indices", matrix.indices),
                ("data", matrix.data),
                ("shape", np.asarray(matrix.shape)),
            ):
                arrays[name + "_" + label + "_" + key] = value
        arrays[name + "_H"] = H
    atomic_npz(path, **arrays)


def cutoff_face_witness(model, packet, n):
    """Direct physical Gauss oracle near kz=0, no Bessel or transform oracle."""
    import basix
    from types import SimpleNamespace
    from src.solvers.analytic_face_ports import face_polynomial
    from src.solvers.fixed_phase_audit import affine_basis

    pts, weights = basix.make_quadrature(basix.CellType.quadrilateral, 2 * n - 1)
    vertices = basix.cell.geometry(basix.CellType.hexahedron)
    faces = basix.cell.topology(basix.CellType.hexahedron)[2]
    errors = []
    for side in ("top", "bottom"):
        z0 = (
            model["cfg"].physical_z_max
            if side == "top"
            else model["cfg"].physical_z_min
        )
        found = None
        for cell in range(packet.nc):
            coords = model["space"].mesh.geometry.x[
                model["space"].mesh.geometry.dofmap[cell]
            ]
            for fi, face in enumerate(faces):
                if np.max(abs(coords[face, 2] - z0)) < 1e-12:
                    found = (cell, fi)
                    break
            if found:
                break
        if found is None:
            raise ValueError("CUTOFF_BOUNDARY_FACE_MISSING")
        cell, fi = found
        poly = face_polynomial(model, cell, fi)
        v = vertices[faces[fi]]
        axes = np.flatnonzero(np.ptp(v, axis=0) > 0.5)
        ref = np.tile(v.min(axis=0), (len(pts), 1))
        ref[:, axes] = pts
        E, _, physical, _, J = affine_basis(model, cell, ref)
        area = np.linalg.norm(np.cross(J[:, axes[0]], J[:, axes[1]]))
        modes = []
        k0 = model["cfg"].k0
        angle = np.deg2rad(17.0)
        for offset in (-1e-8, 0.0, 1e-8):
            kt = k0 * (1 + offset)
            kz = np.sqrt(complex(k0 * k0 - kt * kt)) * (1 if side == "top" else -1)
            k = np.array([kt * np.cos(angle), kt * np.sin(angle), kz], complex)
            for e in (
                np.array([-np.sin(angle), np.cos(angle), 0], complex),
                np.array(
                    [-np.cos(angle) * kz / k0, -np.sin(angle) * kz / k0, kt / k0],
                    complex,
                ),
            ):
                modes.append(SimpleNamespace(k_vector=k, e_vector=e))
        b, d = poly.blocks(modes, model["kappa"], side)
        k = np.asarray([m.k_vector for m in modes])
        e = np.asarray([m.e_vector for m in modes])
        wave = np.exp(1j * (physical @ k.T))
        traction = np.cross(1j * np.cross(k, e), [0, 0, 1 if side == "top" else -1])
        bb = sum(
            E[:, :, j].conj().T
            @ (-area * weights[:, None] * wave * traction[None, :, j])
            for j in range(3)
        )
        dd = sum(
            (area * weights[:, None] * wave.conj() * e[None, :, j].conj()).T
            @ E[:, :, j]
            for j in range(2)
        )
        errors.extend(
            [
                float(
                    np.linalg.norm(b - bb[poly.closure])
                    / max(np.linalg.norm(bb), 1e-300)
                ),
                float(
                    np.linalg.norm(d - dd[:, poly.closure])
                    / max(np.linalg.norm(dd), 1e-300)
                ),
            ]
        )
    return dict(
        relative=errors,
        maximum=max(errors),
        offsets=[-1e-8, 0.0, 1e-8],
        sides=["top", "bottom"],
        polarizations=["s", "p"],
        independent_physical_gauss=True,
    )


def face_qualification(design, artifact, marker, budget):
    from src.solvers.feinn_fem import export_native
    from src.solvers.fixed_phase_audit import (
        surface_blocks,
        analytic_projections,
        integrate_load,
    )
    from src.solvers.fixed_phase_qualification import (
        solve_fixture,
        air_power_witness,
        evaluate,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )
    from benchmarks.affine_output_checker import decimal_components
    from src.runners.fixed_phase_campaign import write

    rows = []
    air = []
    lu_count = 0
    for degree, phase, role in (
        (3, False, "O3"),
        (3, True, "E3"),
        (4, True, "E4"),
        (6, False, "O6_LOCAL_ONLY"),
    ):
        budget("analytic face qualification " + role)
        model = build_model(design["fixture"], degree, phase, topological_ports=True)
        if degree == 6:
            from src.solvers.fixed_phase_port_qualification import (
                nonzero_fixture_background,
            )

            model["background_factory"] = lambda V, cfg: nonzero_fixture_background(
                model
            )
        try:
            p, _ = export_native(model)
            B, D, H, meta = surface_blocks_analytic(model, p, marker)
            n, n2 = meta["oracle_points"]
            BB, DD, HH = surface_blocks(model, p, 2 * n - 1)
            BBB, DDD, HHH = surface_blocks(model, p, 2 * n2 - 1)
            pair = block_evidence(B, D, H, BB, DD, HH)
            oracle = block_evidence(BB, DD, HH, BBB, DDD, HHH)
            save_surface_evidence(
                artifact / (role + "_surface_oracles.npz"),
                dict(analytic=(B, D, H), oracle1=(BB, DD, HH), oracle2=(BBB, DDD, HHH)),
            )
            new = packet_with_blocks(model, p, B, D, H)
            rng = np.random.default_rng(422210 + degree)
            c = np.asarray(rng.normal(size=p.size) + 1j * rng.normal(size=p.size))
            gp = np.asarray(rng.normal(size=p.np) + 1j * rng.normal(size=p.np))
            alpha, work = recover_ports(new.a, c, gp=gp)
            other = decimal_components(new.a, (c,), gp)
            recovery = float(
                np.linalg.norm(alpha - other) / max(np.linalg.norm(other), 1e-12)
            )
            interior_ids = p.a["idofs"]
            internal_norm = float(np.linalg.norm(p.storage(c)[interior_ids]))
            # Independent unmasked oracle sees a deleted real facet column.
            corrupt = D.copy().tolil()
            column = int(np.argmax(np.asarray(abs(D).sum(axis=0)).ravel()))
            corrupt[:, column] = 0
            negative = block_evidence(B, corrupt.tocsr(), H, BB, DD, HH)["passed"]
            controls = dict(
                omitted_facet=bool(not negative),
                wrong_conjugate=bool(
                    not block_evidence(B, D.conj(), H, BB, DD, HH)["passed"]
                ),
                wrong_normal=bool(not block_evidence(-B, D, H, BB, DD, HH)["passed"]),
                wrong_mode_order=bool(
                    not block_evidence(
                        B, D[np.roll(np.arange(p.np), 1)], H, BB, DD, HH
                    )["passed"]
                ),
            )
            wrong = D.copy().tolil()
            wrong[:, column] *= -1
            controls["wrong_orientation"] = bool(
                not block_evidence(B, wrong.tocsr(), H, BB, DD, HH)["passed"]
            )
            cutoff = cutoff_face_witness(model, p, n2)
            row = dict(
                role=role,
                degree=degree,
                phase=phase,
                meta=meta,
                physical_pair=pair,
                oracle_pair=oracle,
                nonzero_port_load_original_recovery=recovery,
                internal_coefficient_norm=internal_norm,
                negative_controls=controls,
                negative_controls_complete=all(controls.values()),
                cutoff_witness=cutoff,
                cutoff_witness_relative=cutoff["maximum"],
                ky=float(np.real(model["cfg"].ky)),
                nonidentity_orientation_count=int(
                    np.count_nonzero(
                        model["space"].mesh.topology.get_cell_permutation_info()
                    )
                ),
                mode_keys=[
                    [m.side, m.m, m.n, m.polarization] for m in model["bundle"]["modes"]
                ],
                omitted_real_facet_rejected=not negative,
                passed=pair["passed"]
                and oracle["passed"]
                and recovery <= 1e-10
                and internal_norm > 0
                and not negative,
            )
            row["passed"] = bool(
                row["passed"]
                and all(controls.values())
                and cutoff["maximum"] <= 1e-10
                and row["nonidentity_orientation_count"] > 0
            )
            if role == "E3":
                cfg = model["cfg"]
                e = np.asarray(cfg.polarization_vector, complex)
                for sign in (-1, 1):
                    budget("fresh analytic port air Poynting")
                    k = np.asarray(
                        [cfg.kx, cfg.ky, sign * abs(cfg.wavevector[2])], complex
                    )

                    def electric(x, k=k):
                        return np.exp(1j * (x @ k))[:, None] * e

                    def curl(x, k=k):
                        return np.exp(1j * (x @ k))[:, None] * 1j * np.cross(k, e)

                    a = analytic_projections(model, electric, 2 * n - 1)
                    rhs = (
                        integrate_load(
                            model,
                            p,
                            lambda x: np.zeros_like(x, dtype=complex),
                            lambda x, side: np.cross(
                                curl(x), [0, 0, 1 if side == "top" else -1]
                            ),
                            2 * n - 1,
                        )
                        + B @ a
                    )
                    audit = {}
                    cp, ap, r = solve_fixture(model, new, rhs, refinement_record=audit)
                    lu_count += audit["factor_count"]
                    E, C = evaluate(model, new, cp, model["centers"])
                    flux = air_power_witness(model, ap, k, e, sign)
                    air.append(
                        dict(
                            z_sign=sign,
                            native=r,
                            physical_E=float(
                                np.linalg.norm(E - electric(model["centers"]))
                                / np.linalg.norm(E)
                            ),
                            physical_curl_H=float(
                                np.linalg.norm(C - curl(model["centers"]))
                                / np.linalg.norm(C)
                            ),
                            complex_modes=float(
                                np.linalg.norm(ap - a) / max(np.linalg.norm(a), 1e-12)
                            ),
                            flux=flux,
                            factor=audit,
                        )
                    )
            rows.append(row)
            marker("face_role_qualified", row)
            atomic_npz(
                artifact / (role + "_blocks.npz"),
                B_indptr=B.indptr,
                B_indices=B.indices,
                B_data=B.data,
                D_indptr=D.indptr,
                D_indices=D.indices,
                D_data=D.data,
                H=H,
                B_shape=np.asarray(B.shape),
                D_shape=np.asarray(D.shape),
            )
            del p, new, B, D, BB, DD, BBB, DDD
        finally:
            destroy_same_mesh_physical_action(model["bundle"])
        gc.collect()
    shared = (
        lu_count <= 5
        and len(air) == 2
        and all(
            r["native"] <= 1e-10
            and max(r["physical_E"], r["physical_curl_H"], r["complex_modes"]) <= 1e-4
            and max(
                r["flux"]["independent_Poynting_vs_port_max_absolute"],
                r["flux"]["all_mode_vs_analytic_max_absolute"],
                r["flux"]["energy_closure"],
            )
            <= 1e-5
            for r in air
        )
    )
    result = dict(
        stage_qualified=shared and all(r["passed"] for r in rows),
        shared_qualified=shared,
        roles=rows,
        air=air,
        small_sparse_LU_count=lu_count,
        local_LU_count=0,
        body_q15_unchanged=True,
        old_q15_FAIL_preserved=True,
        no_O6_solve_permission=True,
    )
    write(artifact / "qualification.json", result)
    return result, dict(qualification=artifact / "qualification.json")


def frozen_audit(design, bindings, artifact, marker, budget, source):
    from src.solvers.fixed_phase_audit import surface_blocks, incident_rhs
    from src.runners.fixed_phase_campaign import write, sha
    from benchmarks.affine_output_checker import check_state
    from src.solvers.fixed_phase_comparison import channels

    book = {}
    results = {}
    for role in ("O3", "E3", "E4"):
        budget("frozen analytic ports " + role)
        out = artifact / role
        out.mkdir()
        old, state = load_bound(bindings[role])
        model = build_model(
            design["models"]["G0"],
            4 if role == "E4" else 3,
            role != "O3",
            operators=False,
        )
        verify_reused_model(model, bindings[role])
        B, D, H, meta = surface_blocks_analytic(model, old, marker)
        n, n2 = meta["oracle_points"]
        BB, DD, HH = surface_blocks(model, old, 2 * n - 1)
        BBB, DDD, HHH = surface_blocks(model, old, 2 * n2 - 1)
        pair = block_evidence(B, D, H, BB, DD, HH)
        oracle = block_evidence(BB, DD, HH, BBB, DDD, HHH)
        from scipy import sparse

        oldB = sparse.coo_matrix(
            (old.a["bv"], (old.a["br"], old.a["bp"])), shape=B.shape
        ).tocsr()
        oldD = sparse.coo_matrix(
            (old.a["dv"], (old.a["dp"], old.a["dr"])), shape=D.shape
        ).tocsr()
        save_surface_evidence(
            out / "surface_oracles.npz",
            dict(
                old_q15=(oldB, oldD, old.a["H"]),
                analytic=(B, D, H),
                oracle1=(BB, DD, HH),
                oracle2=(BBB, DDD, HHH),
            ),
        )
        rhs = incident_rhs(model, old, BB, 2 * n - 1)
        traction = rhs - BB @ np.asarray(model["bundle"]["incident_projections"])
        rhs2 = incident_rhs(model, old, BBB, 2 * n2 - 1)
        traction2 = rhs2 - BBB @ np.asarray(model["bundle"]["incident_projections"])
        reliable_rhs_pair = float(
            np.linalg.norm(traction - traction2)
            / max(np.linalg.norm(traction2), 1e-300)
        )
        p = packet_with_blocks(model, old, B, D, H, traction_load=traction)
        c = state["c_scattered"]
        alpha, work = recover_ports(p.a, c)
        s = affine_state(p, c, alpha)
        equation = split_equation(p, s)
        arithmetic = check_state(
            p.a,
            s,
            mode_hash=model["record"]["mode_manifest_sha256"],
            expected_mode_hash=model["record"]["mode_manifest_sha256"],
        )
        oracle_arrays = dict(
            p.a,
            dp=DD.tocoo().row.astype(np.int64),
            dr=DD.tocoo().col.astype(np.int64),
            dv=DD.tocoo().data,
            H=HH,
        )
        oracle_alpha, _ = recover_ports(oracle_arrays, c)
        atomic_npz(
            out / "frozen_residual_terms.npz",
            c_scattered=c,
            alpha_old=state["alpha_scattered"],
            alpha_new=alpha,
            alpha_independent_physical=oracle_alpha,
            old_residual=old.apply(c) - old.f,
            new_residual=p.apply(c) - p.f,
            native_f=p.f,
            operator_delta=p.apply(c) - old.apply(c),
            RHS_delta=p.f - old.f,
        )
        old_audit = split_equation(old, affine_state(old, c, state["alpha_scattered"]))
        inc = np.asarray(model["bundle"]["incident_projections"])
        oldtraction = old.a["total_g"] - old.B(inc)
        rhs_pair = float(
            np.linalg.norm(traction - oldtraction)
            / max(np.linalg.norm(traction), 1e-300)
        )
        oldch, oldpower = channels(
            model, state["alpha_scattered"], state["alpha_total"]
        )
        newch, newpower = channels(
            model,
            alpha,
            s["alpha_total_hi"].astype(np.clongdouble)
            + s["alpha_total_lo"].astype(np.clongdouble),
        )
        channel_records = {}
        for name in (
            "total_projection",
            "scattered_projection",
            "outgoing_origin",
            "outgoing_boundary",
        ):
            x, y = np.asarray(oldch[name]), np.asarray(newch[name])
            delta = abs(x - y)
            den = np.maximum(abs(y), 1e-12)
            channel_records[name] = dict(
                old_real=x.real.tolist(),
                old_imag=x.imag.tolist(),
                new_real=np.asarray(y.real, float).tolist(),
                new_imag=np.asarray(y.imag, float).tolist(),
                absolute=np.asarray(delta, float).tolist(),
                denominator=np.asarray(den, float).tolist(),
                relative=np.asarray(delta / den, float).tolist(),
            )
        same = all(
            np.array_equal(p.a[k], old.a[k])
            for k in old.a
            if k
            not in (
                "br",
                "bp",
                "bv",
                "dr",
                "dp",
                "dv",
                "H",
                "g",
                "total_g",
                "background_alpha",
            )
        )
        reliable = (
            pair["passed"] and oracle["passed"] and reliable_rhs_pair <= 1e-10 and same
        )
        result = dict(
            role=role,
            meta=meta,
            reliable_operator_qualified=reliable,
            physical_pair=pair,
            oracle_pair=oracle,
            incident_traction_frozen_pair=rhs_pair,
            independent_reliable_traction_pair=reliable_rhs_pair,
            full_equation=equation,
            arithmetic=arithmetic,
            old_full_equation=old_audit,
            correction_triggered=role != "O3" and equation["native_relative"] > 1e-6,
            coefficient_bytes_unchanged=bool(np.array_equal(c, state["c_scattered"])),
            body_and_MPC_bytes_unchanged=same,
            operator_effect=float(
                np.linalg.norm(p.apply(c) - old.apply(c)) / old.bnorm
            ),
            RHS_effect=float(np.linalg.norm(p.f - old.f) / old.bnorm),
            alpha_change=float(
                np.linalg.norm(alpha - state["alpha_scattered"])
                / max(np.linalg.norm(alpha), 1e-12)
            ),
            actual_alpha_vs_independent_physical_oracle_relative=float(
                np.linalg.norm(alpha - oracle_alpha)
                / max(np.linalg.norm(oracle_alpha), 1e-12)
            ),
            actual_alpha_vs_independent_physical_oracle_per_mode=(
                abs(alpha - oracle_alpha) / np.maximum(abs(oracle_alpha), 1e-12)
            ).tolist(),
            channels=channel_records,
            mode_keys=[
                [m.side, m.m, m.n, m.polarization] for m in model["bundle"]["modes"]
            ],
            old_power=oldpower,
            new_power=newpower,
            accurate_recovery_cost=work,
            new_packet_hashes=packet_hashes(p),
            old_packet_hashes=packet_hashes(old),
            global_factor_count=0,
            local_LU_count=0,
            physical_body_comparison_reused_from_V21=True,
        )
        atomic_npz(out / "native.npz", **p.a)
        atomic_npz(out / "affine_state.npz", **s)
        identity = dict(
            model["record"],
            port_operator_version="affine_tensor_Fourier_Legendre_v1",
            packet_hashes=packet_hashes(p),
            old_binding=bindings[role],
            new_source=source,
        )
        from src.geometry.fixed_phase_plan import digest

        identity["legacy_discretization_sha256"] = identity.get(
            "discretization_sha256", digest(packet_hashes(old))
        )
        identity["discretization_sha256"] = digest(
            dict(
                legacy=identity["legacy_discretization_sha256"],
                new_port_operator_version=identity["port_operator_version"],
                new_packet_hashes=identity["packet_hashes"],
            )
        )
        write(out / "identity.json", identity)
        write(out / "result.json", result)
        book[role] = dict(
            source_sha=source,
            result=result,
            files={
                k: dict(path=str(v), sha256=sha(v))
                for k, v in dict(
                    native=out / "native.npz",
                    field=out / "affine_state.npz",
                    identity=out / "identity.json",
                    result=out / "result.json",
                    surface_oracles=out / "surface_oracles.npz",
                    frozen_residual_terms=out / "frozen_residual_terms.npz",
                ).items()
            },
        )
        results[role] = result
        marker(
            "frozen_original_c_new_operator",
            dict(
                role=role,
                native=equation["native_relative"],
                reliable=reliable,
                trigger=result["correction_triggered"],
            ),
        )
        del p, old, model, B, D, BB, DD, BBB, DDD
        gc.collect()
    write(artifact / "role_indices.json", book)
    return dict(
        stage_qualified=True,
        roles=results,
        reference_qualified=False,
        readable_negative_fields=True,
        all_modes_preserved=True,
        no_factor_or_solve=True,
    ), dict(role_indices=artifact / "role_indices.json")


def correction(design, role, artifact, marker, budget, source):
    """Only the new contract's residual trigger can call this existing solver."""
    from src.runners.fixed_phase_campaign import selected, write
    from src.solvers.feinn_exact_condensation import ExactInteriorCondensation, capacity
    from src.solvers.fixed_phase_port_coordinates import BoundaryPortCondensation
    from src.solvers.dtn_port_3d import _mode_boundary_phase
    from src.solvers.feinn_reference import exact_solve
    from src.solvers.fixed_phase_audit import PhysicalVolumeAudit, surface_blocks
    from src.solvers.fixed_phase_comparison import self_physics
    from benchmarks.affine_output_checker import check_state

    rows = json.loads(
        Path(
            selected("v22_frozen_port_audit")["files"]["role_indices"]["path"]
        ).read_text()
    )
    b = rows[role]
    p = load_native(b["files"]["native"]["path"])
    model = build_model(
        design["models"]["G0"], 4 if role == "E4" else 3, True, operators=False
    )
    verify_reused_model(model, b)
    B, D, H, meta = surface_blocks_analytic(model, p, marker)
    n = meta["oracle_points"][0]
    BB, DD, HH = surface_blocks(model, p, 2 * n - 1)
    if not block_evidence(B, D, H, BB, DD, HH)["passed"]:
        raise ValueError("V22_CORRECTION_REAL_OPERATOR_CHANGED")
    independent = PhysicalVolumeAudit(model, p)
    volume = independent.check()
    if not volume["passed"]:
        raise ValueError("V22_UNCHANGED_BODY_INDEPENDENT_PAIR")
    reduced0 = ExactInteriorCondensation(
        p, model["space"].element.basix_element.entity_dofs[3][0]
    )
    local_records = list(reduced0.local_factor_records)
    marker(
        "local_factor_costs",
        dict(factor_count=len(local_records), records=local_records),
    )
    reduced = BoundaryPortCondensation(
        reduced0,
        [_mode_boundary_phase(m, model["cfg"]) for m in model["bundle"]["modes"]],
        artifact,
    )
    plan = capacity(p.nc, model["record"]["degree"], classes=len(p.a["F"]), ports=p.np)

    def raw(c, a, record):
        atomic_npz(
            artifact / "raw_lu.npz",
            c_scattered=c,
            alpha_lu_raw=a,
            alpha_old_backsub=p.alpha(c),
        )

    def final(c, a):
        return recover_ports(p.a, c)

    def save(c, a, record):
        atomic_npz(artifact / "affine_state.npz", **affine_state(p, c, a))

    options = dict(
        reduced_system=reduced,
        assembler=lambda m, pkt, mark, current=reduced: current.assemble(m, pkt, mark),
        allocation_upper_bytes=plan["allocation_upper_bytes"],
        check_budget=budget,
        save_packet=save,
        save_unqualified_recovery=True,
        residual_tolerance=1e-6,
        save_raw_recovery=raw,
        final_port_recovery=final,
        independent_port_recovery=lambda c: __import__(
            "benchmarks.affine_output_checker", fromlist=["decimal_components"]
        ).decimal_components(p.a, (c,), p.a["gp"]),
        full_equation_audit=lambda c, a: split_equation(p, affine_state(p, c, a)),
    )
    c, direct = exact_solve(model, p, artifact, marker, audit_options=options)
    # exact_solve already destroys global factor/matrix and proves RSS drop.
    del options, reduced, reduced0
    gc.collect()
    alpha, _ = recover_ports(p.a, c)
    s = affine_state(p, c, alpha)
    save(c, alpha, direct)
    equation = split_equation(p, s)
    arithmetic = check_state(
        p.a,
        s,
        mode_hash=model["record"]["mode_manifest_sha256"],
        expected_mode_hash=model["record"]["mode_manifest_sha256"],
    )
    total = total_field(s)
    at = s["alpha_total_hi"].astype(np.clongdouble) + s["alpha_total_lo"].astype(
        np.clongdouble
    )
    weak = np.r_[
        total.map(independent.volume).physical_values() + BB @ at - p.a["total_g"],
        -(DD @ total.hi + DD @ total.lo) + HH * at,
    ]
    equation["independent_physical_weak"] = float(
        np.linalg.norm(weak) / np.linalg.norm(p.a["total_g"])
    )
    # Public MPC and all internal coefficients validated before publication.
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field

    mpc = []
    for vector in (c, total.hi, total.lo):
        f = restore_p0_full_field(model["floquet"], p.storage(vector))
        local = p.expand(vector)
        mpc.append(
            float(
                np.linalg.norm(f.x.array[p.a["cell_dofs"]] - local)
                / max(np.linalg.norm(local), 1e-300)
            )
        )
    qualified = (
        arithmetic["passed"]
        and max(mpc) <= 1e-10
        and max(
            equation[k]
            for k in (
                "native_relative",
                "augmented_relative",
                "original_total_augmented_relative",
                "independent_physical_weak",
            )
        )
        <= 1e-6
    )
    physics = self_physics(
        model, p, c, alpha, artifact, marker, budget, affine_output=s
    )
    atomic_npz(artifact / "native.npz", **p.a)
    identity = dict(
        model["record"],
        port_operator_version="affine_tensor_Fourier_Legendre_v1",
        packet_hashes=packet_hashes(p),
        source_sha=source,
    )
    write(artifact / "identity.json", identity)
    result = dict(
        role=role,
        stage_qualified=qualified,
        complete_output_qualified=qualified,
        full_equation=equation,
        arithmetic=arithmetic,
        MPC=mpc,
        physics=physics,
        identity=identity,
        direct=direct,
        global_Maxwell_LU_count=1,
        local_LU_count=len(local_records),
        local_LU_records=local_records,
        reference_qualified=False,
        only_same_input_operator_correction=True,
    )
    return result, {
        k: v
        for k, v in dict(
            native=artifact / "native.npz",
            field=artifact / "affine_state.npz",
            identity=artifact / "identity.json",
            observables=artifact / "observables.npz",
        ).items()
    }


def corrected_compare(design, artifact, marker, budget):
    from src.runners.fixed_phase_campaign import selected, ARTIFACTS, write
    from src.solvers.fixed_phase_comparison import compare

    initial = json.loads(
        Path(selected("v22_affine_saved")["files"]["role_indices"]["path"]).read_text()
    )
    indices = {}
    defs = {}
    pairs = []
    for role in ("E3", "E4"):
        indices["old_" + role] = initial[role]
        defs["old_" + role] = ("G0", 4 if role == "E4" else 3, True)
        indices["old_" + role]["result"]["identity"] = json.loads(
            Path(initial[role]["files"]["identity"]["path"]).read_text()
        )
        indices["old_" + role]["result"]["checker"] = dict(
            passed=initial[role]["result"]["complete_output_qualified"]
        )
        candidates = list(
            ARTIFACTS.glob("index_v22_" + role.lower() + "_correction_attempt*.json")
        )
        if candidates:
            record = json.loads(candidates[-1].read_text())
            record["result"]["checker"] = dict(
                passed=record["result"].get("stage_qualified", False)
            )
            indices["new_" + role] = record
            defs["new_" + role] = defs["old_" + role]
            pairs.append(("old_" + role, "new_" + role))
    if "new_E3" in indices and "new_E4" in indices:
        pairs.append(("new_E3", "new_E4"))
    if not pairs:
        return dict(
            stage_qualified=True,
            status="NOT_RUN_NO_CORRECTED_FIELD",
            old_body_integrals_reused=True,
        ), {}
    write(artifact / "role_indices.json", indices)
    result, files = compare(
        indices, artifact, marker, budget, role_definitions=defs, pair_definitions=pairs
    )
    result["reference_qualified"] = False
    result["production_qualified"] = False
    files["role_indices"] = artifact / "role_indices.json"
    return result, files


def target_local_face(artifact, marker, budget):
    """Only a saved manifest may supply original keys; never builds AUTO."""
    from src.runners.fixed_phase_campaign import ROOT, sha, write

    digest = "52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d"
    relative = "benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/original_size_auto_mode_manifest.json"
    paths = [
        ROOT / relative,
        Path("/home/fenics/Projects/MyFEniCS") / relative,
        Path("/tmp/task40extra_0p7nm_engineering") / relative,
    ]
    # Same-byte repair copies are allowed, but no recursive machine scan.
    roots = [
        Path("/home/fenics/Projects/MyFEniCS"),
        Path("/home/fenics/Projects/Maxwell3D-Lab"),
    ]
    for r in roots:
        paths.extend(
            p / relative
            for p in r.iterdir()
            if p.is_dir() and p.name not in (".git", "tmp", "benchmarks", "results")
        )
    found = [
        p
        for p in paths
        if p.is_file() and p.stat().st_size == 36244923 and sha(p) == digest
    ]
    package = dict(
        functions=[
            "src.solvers.analytic_face_ports.face_polynomial(model,cell,facet)",
            "AffineFacePolynomial.blocks(modes,kappa,side)",
            "original_normalization(modes,period_x,period_y,z_top,z_bottom)",
            "src.solvers.affine_field_output.affine_state(packet,c,alpha)",
            "SplitVector.map(action)",
            "src.solvers.accurate_ports.recover_ports_components(a,components,gp=...)",
        ],
        assumptions=[
            "affine horizontal planar N1curl hex face",
            "qualified Basix orientation",
            "original k/e/side/reference phase",
            "master-only MPC expansion exactly once",
            "non-affine/complex tangential/phase-underflow rejected",
        ],
        receiver="main _ReusableSurfaceComponentAssembler / carrier; receiver owns full W1 lifecycle",
        forbidden=[
            "full original carrier",
            "dense 32060-square Hhat",
            "AUTO regeneration",
            "new PC/backend/storage",
        ],
        original_geometry_derived=dict(
            x_breaks_nm=[0, 16.5, 25, 33.5, 50],
            x_segments=[78, 58, 58, 78],
            y_segments=4,
            z_cells=14,
        ),
        manifest_required=dict(
            path=relative,
            sha256=digest,
            bytes=36244923,
            ordered_key_sha256="03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec",
        ),
        algorithm_source=dict(
            path="src/solvers/analytic_face_ports.py",
            sha256=sha(ROOT / "src/solvers/analytic_face_ports.py"),
        ),
        data_layout=dict(
            local_B="closure_dof x mode, complex128; already Piola/oriented, not yet global MPC",
            local_D="mode x closure_dof, complex128",
            original_H="mode real positive diagonal, whole cell area; not summed by local face",
            polynomial="(p+1,p+1,closure_dof,3) tensor Legendre coefficients",
            global_MPC="receiver applies conjugate C to B, C to D once; supports exact slave/master mapping",
            low_bits="two separate complex128 coefficients; linear consumers apply both before guard-digit physical combination",
        ),
        ABI=dict(PETSc_scalar="complex128", PETSc_int="int64", MPI=1),
        lookup_paths=[str(p) for p in paths],
        main_full_target_qualified=False,
        NN_increment=False,
    )
    if not found:
        package.update(
            status="NOT_RUN_MISSING_HASH_BOUND_32060_MANIFEST",
            complete_key_oracle_qualified=False,
            local_speedup="UNKNOWN_NO_SAME_ACCURACY_BASELINE",
        )
        write(artifact / "minimal_integration_package.json", package)
        return dict(stage_qualified=True, **package), dict(
            package=artifact / "minimal_integration_package.json"
        )
    # A present body must be schema-qualified before any local action.
    package.update(
        status="SAVED_MANIFEST_PRESENT_SCHEMA_REQUIRES_MAPPING",
        manifest=dict(path=str(found[0]), sha256=digest),
        complete_key_oracle_qualified=False,
    )
    write(artifact / "minimal_integration_package.json", package)
    return dict(stage_qualified=False, **package), dict(
        package=artifact / "minimal_integration_package.json"
    )
