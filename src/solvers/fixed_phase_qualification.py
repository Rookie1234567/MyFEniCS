"""Joint independent qualification of the opt-in physical g*Vh space."""

import gc
import numpy as np
from scipy.sparse.linalg import splu

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


def solve_fixture(model, packet, load, alpha_load=None, *, refinement_record=None):
    from src.solvers.feinn_authority_assembly import packet_csr
    from src.solvers.feinn_native import FullNativePacket

    alpha_load = np.zeros(packet.np, complex) if alpha_load is None else alpha_load
    custom = FullNativePacket(dict(packet.a, g=load, gp=alpha_load))
    M, _ = packet_csr(model, custom)
    rhs = np.r_[load, alpha_load]
    # One small-fixture LU, reused for bounded defect correction. The nearly
    # grazing plane wave has a small rhs after cancellation of volume terms;
    # sparse-direct success alone is insufficient for the original residual.
    factor = splu(M.tocsc())
    x = factor.solve(rhs)
    residuals = [float(np.linalg.norm(M @ x - rhs) / np.linalg.norm(rhs))]
    for _ in range(3):
        if residuals[-1] <= 1e-10:
            break
        corrected = x + factor.solve(rhs - M @ x)
        relative_residual = float(
            np.linalg.norm(M @ corrected - rhs) / np.linalg.norm(rhs)
        )
        residuals.append(relative_residual)
        if relative_residual >= residuals[-2]:
            break
        x = corrected
    if refinement_record is not None:
        refinement_record.update(
            original_relative_residuals=residuals,
            factor_count=1,
            maximum_defect_corrections=3,
            accepted_relative_residual=float(
                np.linalg.norm(M @ x - rhs) / np.linalg.norm(rhs)
            ),
        )
    r = M @ x - rhs
    return (
        x[: packet.size],
        x[packet.size :],
        float(np.linalg.norm(r) / np.linalg.norm(np.r_[load, alpha_load])),
    )


def qualify(design, marker=lambda *_: None, *, joint_ports=False):
    from src.solvers.feinn_fem import export_native, native_gate
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )

    gates, details = {}, {}
    zero = build_model(design, 3, False, marker=marker, topological_ports=joint_ports)
    same = build_model(design, 3, True, fixture_zero_carrier=True, marker=marker,
                       topological_ports=joint_ports)
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
        if joint_ports:
            from src.solvers.fixed_phase_fem import physical_rhs
            from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import build_physical_rhs
            new, _ = physical_rhs(zero["bundle"])
            old, _ = build_physical_rhs(zero["bundle"])
            try:
                details["zero_carrier_old_rhs_relative"] = relative(new.array,old.array)
            finally:
                new.destroy()
                old.destroy()
    finally:
        destroy_same_mesh_physical_action(zero["bundle"])
        destroy_same_mesh_physical_action(same["bundle"])
    del zero, same, p0, pz
    gc.collect()
    model = build_model(design, 3, True, marker=marker, topological_ports=joint_ports)
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
        manufactured_refinement = {}
        solved, solved_alpha, residual = solve_fixture(
            model, p, load, refinement_record=manufactured_refinement
        )
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
            plane_refinement = {}
            cp, ap, rp = solve_fixture(
                model, p, plane_load, refinement_record=plane_refinement
            )
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
                    direct_refinement=plane_refinement,
                )
            )
            if joint_ports:
                plane[-1]["physical_flux"] = air_power_witness(model,ap,k,e,sign)
        gates["air_plane_residual"] = max(row["original_residual"] for row in plane)
        gates["air_plane_fields_channels"] = max(
            row[k]
            for row in plane
            for k in ("physical_E", "physical_curl_H", "complex_channels")
        )
        gates["air_plane_power"] = max(row["power_absolute"] for row in plane)
        if joint_ports:
            gates["air_plane_power"] = max(
                row["physical_flux"]["all_mode_vs_analytic_max_absolute"] for row in plane)
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
            manufactured_direct_refinement=manufactured_refinement,
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


def air_power_witness(model, actual, k, e, sign):
    """Independent E cross H* Poynting power, all physical modes/directions."""
    from src.common.modes_3d import incident_power_3d
    from src.solvers.dtn_port_3d import _mode_power_at_boundary, _mode_carries_outward_power

    cfg, modes = model["cfg"], model["bundle"]["modes"]
    incoming_side = "top" if sign == -1 else "bottom"
    outgoing_side = "bottom" if sign == -1 else "top"
    incoming = np.zeros(len(modes),complex)
    exact = np.zeros_like(incoming)
    for j,m in enumerate(modes):
        if m.m == 0 and m.n == 0:
            z = cfg.physical_z_max if m.side == "top" else cfg.physical_z_min
            value = (np.vdot(m.e_vector[:2],e[:2])
                     / np.vdot(m.e_vector[:2],m.e_vector[:2]).real
                     * np.exp(1j*(k[2]-m.k_vector[2])*z))
            if m.side == incoming_side:
                incoming[j] = value
            else:
                exact[j] = value
    outgoing = actual-incoming
    direct, expected, port = [], [], []
    for j,m in enumerate(modes):
        z = cfg.physical_z_max if m.side == "top" else cfg.physical_z_min

        def flux(alpha):
            E = alpha*np.exp(1j*m.k_vector[2]*z)*np.asarray(m.e_vector)
            H = np.cross(m.k_vector,E)/(cfg.k0*cfg.mu_r)
            return max(float(.5*np.cross(E,H.conj())[2].real
                             *(1 if m.side == "top" else -1)
                             *cfg.period_x*cfg.period_y/incident_power_3d(cfg)),0)
        direct.append(flux(outgoing[j]))
        expected.append(flux(exact[j]))
        port.append(_mode_power_at_boundary(m,cfg,outgoing[j])/incident_power_3d(cfg)
                    if _mode_carries_outward_power(m) else 0)
    direct,expected,port = map(np.asarray,(direct,expected,port))
    return dict(channels=len(modes),z_sign=sign,incoming_side=incoming_side,
                outgoing_side=outgoing_side,
                per_mode_physical_power=direct.tolist(),per_mode_analytic_power=expected.tolist(),
                independent_Poynting_vs_port_max_absolute=float(max(abs(direct-port))),
                all_mode_vs_analytic_max_absolute=float(max(abs(direct-expected))),
                reflected=float(sum(direct[j] for j,m in enumerate(modes) if m.side==incoming_side)),
                transmitted=float(sum(direct[j] for j,m in enumerate(modes) if m.side==outgoing_side)),
                energy_closure=float(abs(sum(direct)-1)),physical_E_cross_H=True)
