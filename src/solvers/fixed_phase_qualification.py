"""Joint independent qualification of the opt-in physical g*Vh space."""

import gc
import numpy as np
from scipy.sparse.linalg import spsolve

from src.solvers.fixed_phase_audit import (
    PhysicalVolumeAudit,
    affine_basis,
    surface_blocks,
    block_pair,
    integrate_load,
    analytic_projections,
    incident_rhs,
)
from src.solvers.fixed_phase_fem import build_model


def relative(a, b):
    return float(np.linalg.norm(a - b) / max(np.linalg.norm(b), 1e-30))


def coefficients(model, packet, envelope):
    import basix.ufl
    from dolfinx import fem
    from src.solvers.feinn_interpolation import full_moment_element
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field

    custom = full_moment_element(model["space"].element.basix_element, 15)
    V = fem.functionspace(model["data"].mesh, basix.ufl.wrap_element(custom))
    f = fem.Function(V)
    f.interpolate(lambda x: envelope(x.T).T)
    c = f.x.array[packet.a["masters"]].copy()
    restored = restore_p0_full_field(model["floquet"], packet.storage(c))
    return c, relative(restored.x.array, f.x.array)


def evaluate(model, packet, c, points):
    """Saved master coefficients, physical basis and exact affine cell map."""
    local = packet.expand(c)
    out_e, out_c = [], []
    for x in points:
        cell = None
        for i in np.argsort(np.linalg.norm(model["centers"] - x, axis=1)):
            coords = model["data"].mesh.geometry.x[
                model["data"].mesh.geometry.dofmap[i]
            ]
            if np.all(x >= coords.min(axis=0) - 1e-12) and np.all(
                x <= coords.max(axis=0) + 1e-12
            ):
                cell = int(i)
                break
        if cell is None:
            raise ValueError("SAMPLE_OUTSIDE_DOMAIN")
        coords = model["data"].mesh.geometry.x[model["data"].mesh.geometry.dofmap[cell]]
        import basix

        X = np.column_stack(
            (np.ones(8), basix.cell.geometry(basix.CellType.hexahedron))
        )
        fit = np.linalg.lstsq(X, coords, rcond=None)[0]
        ref = np.linalg.solve(fit[1:].T, x - fit[0])[None]
        E, C, _, _, _ = affine_basis(model, cell, ref)
        out_e.append(np.einsum("qia,i->qa", E, local[cell])[0])
        out_c.append(np.einsum("qia,i->qa", C, local[cell])[0])
    return np.asarray(out_e), np.asarray(out_c)


def manufactured(model):
    k = model["kappa"]

    def values(x):
        z = x[:, 2]
        u = np.column_stack(
            (1 + z + 0.2j * z * z, 0.7 - 0.1j * z + z * z, 1 + 0.3j * z)
        )
        uz = np.column_stack((1 + 0.4j * z, -0.1j + 2 * z, np.full(len(z), 0.3j)))
        uzz = np.tile([0.4j, 2, 0], (len(z), 1))
        C = np.cross([0, 0, 1], uz) + 1j * np.cross(k, u)
        Cz = np.cross([0, 0, 1], uzz) + 1j * np.cross(k, uz)
        CC = np.cross([0, 0, 1], Cz) + 1j * np.cross(k, C)
        g = np.exp(1j * (x @ k))[:, None]
        return u, g * u, g * C, g * (CC - model["cfg"].k0 ** 2 * u)

    return values


def solve_fixture(model, packet, load, alpha_load=None):
    from src.solvers.feinn_authority_assembly import packet_csr
    from src.solvers.feinn_native import FullNativePacket

    alpha_load = np.zeros(packet.np, complex) if alpha_load is None else alpha_load
    custom = FullNativePacket(dict(packet.a, g=load, gp=alpha_load))
    M, _ = packet_csr(model, custom)
    x = spsolve(M, np.r_[load, alpha_load])
    r = M @ x - np.r_[load, alpha_load]
    return (
        x[: packet.size],
        x[packet.size :],
        float(np.linalg.norm(r) / np.linalg.norm(np.r_[load, alpha_load])),
    )


def qualify(design, marker=lambda *_: None):
    from src.solvers.feinn_fem import export_native, native_gate
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )

    gates, details = {}, {}
    zero = build_model(design, 3, False, marker=marker)
    same = build_model(design, 3, True, fixture_zero_carrier=True, marker=marker)
    try:
        p0, _ = export_native(zero, marker)
        pz, _ = export_native(same, marker)
        rng = np.random.default_rng(422020)
        rows = []
        for _ in range(3):
            c = rng.normal(size=p0.size) + 1j * rng.normal(size=p0.size)
            a = rng.normal(size=p0.np) + 1j * rng.normal(size=p0.np)
            rows.append(
                max(
                    relative(p0.volume(c), pz.volume(c)),
                    relative(p0.B(a), pz.B(a)),
                    relative(p0.D(c), pz.D(c)),
                )
            )
        gates["zero_carrier"] = max(
            rows
            + [
                relative(p0.a["total_g"], pz.a["total_g"]),
                relative(p0.a["background"], pz.a["background"]),
            ]
        )
        details["zero_carrier_nonzero_vectors"] = rows
    finally:
        destroy_same_mesh_physical_action(zero["bundle"])
        destroy_same_mesh_physical_action(same["bundle"])
    del zero, same, p0, pz
    gc.collect()
    model = build_model(design, 3, True, marker=marker)
    try:
        p, info = export_native(model, marker)
        va = PhysicalVolumeAudit(model, p)
        volume = va.check()
        gates["physical_volume"] = max(volume["relative"])
        B, D, H = surface_blocks(model, p)
        ports = block_pair(p, B, D, H)
        gates["physical_B_D_H"] = max(v for row in ports["samples"] for v in row)
        gates["physical_rhs"] = relative(incident_rhs(model, p, B), p.a["total_g"])
        native = native_gate(model, p)
        gates["native_adjoint_and_port_load"] = max(
            v
            for row in native["samples"]
            for k, v in row.items()
            if k != "arbitrary_interior_norm"
        )
        gates["nonzero_port_rhs"] = max(
            native["nonzero_FE_and_port_load_relative"],
            native["nonzero_port_load_operation_relative"],
        )
        fun = manufactured(model)
        c, recovery = coefficients(model, p, lambda x: fun(x)[0])
        alpha = analytic_projections(model, lambda x: fun(x)[1])

        def traction(x, side):
            return np.cross(fun(x)[2], [0, 0, 1 if side == "top" else -1])

        load = integrate_load(model, p, lambda x: fun(x)[3], traction) + B @ alpha
        # Source is independently differentiated Maxwell, not packet.apply(c).
        gates["manufactured_original_weak"] = relative(p.volume(c) + B @ alpha, load)
        gates["manufactured_port"] = relative(D @ c, H * alpha)
        solved, solved_alpha, residual = solve_fixture(model, p, load)
        gates["manufactured_solve_residual"] = residual
        gates["manufactured_solve_field"] = relative(solved, c)
        gates["manufactured_recovery"] = recovery
        x = np.asarray(
            [
                [0, 0.031, 0.023],
                [model["cfg"].period_x, 0.031, 0.023],
                [0.033, 0, 0.023],
                [0.033, model["cfg"].period_y, 0.023],
                [0, 0, 0.023],
                [model["cfg"].period_x, model["cfg"].period_y, 0.023],
            ]
        )
        E, C = evaluate(model, p, c, x)
        cfg = model["cfg"]
        known_bg = np.exp(1j * (x @ np.asarray(cfg.wavevector)))[:, None] * np.asarray(
            cfg.polarization_vector
        )
        bgE, bgC = evaluate(model, p, p.a["background"], x)
        gates["physical_background"] = max(
            relative(bgE, known_bg),
            relative(bgC, 1j * np.cross(np.asarray(cfg.wavevector), known_bg)),
        )
        scatE, scatC = evaluate(model, p, c - p.a["background"], x)
        gates["total_scattered_affine_closure"] = max(
            relative(scatE + bgE, E), relative(scatC + bgC, C)
        )
        gates["physical_floquet_x_y_corner"] = max(
            relative(E[1], cfg.floquet_phase_x * E[0]),
            relative(E[3], cfg.floquet_phase_y * E[2]),
            relative(E[5], cfg.floquet_phase_x * cfg.floquet_phase_y * E[4]),
        )
        gates["physical_H_manufactured"] = relative(C, fun(x)[2])
        # Integration by parts of div(curl curl E)=0 with a scalar test
        # vanishing at z boundaries; periodic envelope lateral traces cancel.
        import basix

        qp, qw = basix.make_quadrature(basix.CellType.hexahedron, 15)
        gauss, scale = 0j, 0.0
        z0, z1 = cfg.physical_z_min, cfg.physical_z_max
        for cell in range(p.nc):
            _, _, xx, det, _ = affine_basis(model, cell, qp)
            z = xx[:, 2]
            phi = (z - z0) * (z1 - z)
            grad = np.exp(1j * (xx @ model["kappa"]))[:, None] * (
                1j * phi[:, None] * model["kappa"]
                + np.column_stack((np.zeros(len(z)), np.zeros(len(z)), z0 + z1 - 2 * z))
            )
            CC = fun(xx)[3] + cfg.k0**2 * fun(xx)[1]
            gauss += det * np.sum(qw * np.sum(CC * grad.conj(), axis=1))
            scale += det * np.sum(
                qw * np.linalg.norm(CC, axis=1) * np.linalg.norm(grad, axis=1)
            )
        gates["manufactured_Gauss_weak"] = float(abs(gauss) / max(scale, 1e-30))
        vb = PhysicalVolumeAudit(model, p, 30)
        BB, DD, HH = surface_blocks(model, p, 30)
        rng = np.random.default_rng(422021)
        cq = rng.normal(size=p.size) + 1j * rng.normal(size=p.size)
        aq = rng.normal(size=p.np) + 1j * rng.normal(size=p.np)
        gates["quadrature_15_30"] = max(
            relative(vb.volume(cq), va.volume(cq)),
            relative(BB @ aq, B @ aq),
            relative(DD @ cq, D @ cq),
            relative(HH, H),
            relative(incident_rhs(model, p, BB, 30), p.a["total_g"]),
        )
        plane = []
        e = np.asarray(cfg.polarization_vector, complex)
        for sign in (-1, 1):
            k = np.asarray([cfg.kx, cfg.ky, sign * abs(cfg.wavevector[2])], complex)

            def electric(xx, k=k):
                return np.exp(1j * (xx @ k))[:, None] * e

            def curl(xx, k=k):
                return np.exp(1j * (xx @ k))[:, None] * 1j * np.cross(k, e)

            a = analytic_projections(model, electric)
            plane_load = (
                integrate_load(
                    model,
                    p,
                    lambda xx: np.zeros_like(xx, dtype=complex),
                    lambda xx, side: np.cross(
                        curl(xx), [0, 0, 1 if side == "top" else -1]
                    ),
                )
                + B @ a
            )
            cp, ap, rp = solve_fixture(model, p, plane_load)
            sample = model["centers"]
            ep, hp = evaluate(model, p, cp, sample)
            plane.append(
                dict(
                    z_sign=sign,
                    original_residual=rp,
                    physical_E=relative(ep, electric(sample)),
                    physical_curl_H=relative(hp, curl(sample)),
                    complex_channels=relative(ap, a),
                    power_absolute=float(np.max(abs(abs(ap) ** 2 - abs(a) ** 2))),
                )
            )
        gates["air_plane_residual"] = max(row["original_residual"] for row in plane)
        gates["air_plane_fields_channels"] = max(
            row[k]
            for row in plane
            for k in ("physical_E", "physical_curl_H", "complex_channels")
        )
        gates["air_plane_power"] = max(row["power_absolute"] for row in plane)
        # Actual dangerous inputs: use the same independent reference to reject
        # omitted carrier curl, twice-applied phase and an incomplete volume load.
        wrong = dict(model, kappa=np.zeros(3))
        bad_volume = PhysicalVolumeAudit(wrong, p).check()["relative"]
        doubled = dict(model, kappa=2 * model["kappa"])
        wrong_B, wrong_D, wrong_H = surface_blocks(doubled, p)
        from dataclasses import replace

        bad_modes = [
            replace(
                m,
                alpha=m.alpha - cfg.kx,
                gamma=m.gamma - cfg.ky,
                k_vector=np.asarray(m.k_vector) - np.asarray([cfg.kx, cfg.ky, 0]),
            )
            for m in model["bundle"]["modes"]
        ]
        wrong_ports = dict(model, bundle=dict(model["bundle"], modes=bad_modes))
        wrong_PB, wrong_PD, wrong_PH = surface_blocks(wrong_ports, p)
        from src.solvers.common_3d_fields import stage4_layered_background_field

        legacy_bg = stage4_layered_background_field(model["space"], cfg).x.array[
            p.a["masters"]
        ]
        badbgE, _ = evaluate(model, p, legacy_bg, x)
        missing = load.copy()
        lookup = {int(v): i for i, v in enumerate(p.a["masters"])}
        interior = np.array([lookup[int(v)] for v in p.a["idofs"].ravel()])
        missing[interior] = 0
        details.update(
            volume=volume,
            ports=ports,
            native=native,
            plane=plane,
            identity=info,
            manufactured_source="analytic curl curl E-k0^2 E with independent physical boundary traction",
            negative_controls=dict(
                omitted_curl_difference=max(bad_volume),
                double_phase_difference=max(
                    v
                    for row in block_pair(p, wrong_B, wrong_D, wrong_H)["samples"]
                    for v in row
                ),
                omitted_internal_rhs_difference=relative(missing, load),
                incorrect_physical_ports_difference=max(
                    v
                    for row in block_pair(p, wrong_PB, wrong_PD, wrong_PH)["samples"]
                    for v in row
                ),
                old_background_difference=relative(badbgE, bgE),
            ),
            all_dof_families={
                str(i): sum(
                    len(v) for v in model["space"].element.basix_element.entity_dofs[i]
                )
                for i in (1, 2, 3)
            },
            ky=float(cfg.ky.real),
            no_producer_F_read_in_physical_audit=True,
        )
        return dict(schema="fixed_phase.qualification.v1", gates=gates, details=details)
    finally:
        destroy_same_mesh_physical_action(model["bundle"])
