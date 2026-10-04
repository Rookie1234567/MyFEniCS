"""Small FE-only construction/field checks, not a B solve lifecycle."""

import sys
import numpy as np

from src.geometry.fixed_phase_plan import fixture_design
from src.solvers.fixed_phase_fem import build_model, carrier


def test_small_mesh_envelope_and_physical_wavenumber():
    model = build_model(fixture_design(), 3, True, operators=False)
    cfg = model["cfg"]
    assert abs(cfg.ky) > 0
    assert np.allclose(model["kappa"], [cfg.kx, cfg.ky, 0], rtol=0, atol=1e-14)
    assert abs(cfg.floquet_phase_x - 1) > 1e-2
    assert len(model["bundle"]["modes"]) == 36
    assert model["record"]["cells"] == 8
    assert (
        model["space"].dofmap.index_map.size_local - len(model["floquet"].mpc.slaves)
        == 720
    )
    assert all(
        abs(m.alpha - (cfg.kx + 2 * np.pi * m.m / cfg.period_x)) < 1e-12
        for m in model["bundle"]["modes"]
    )
    assert all(
        abs(m.gamma - (cfg.ky + 2 * np.pi * m.n / cfg.period_y)) < 1e-12
        for m in model["bundle"]["modes"]
    )
    assert np.array_equal(carrier(cfg, False), [0, 0, 0])
    assert "torch" not in sys.modules


def test_small_independent_physical_volume_and_ports():
    from src.solvers.feinn_fem import export_native
    from src.solvers.fixed_phase_audit import (
        PhysicalVolumeAudit,
        surface_blocks,
        block_pair,
        incident_rhs,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )

    model = build_model(fixture_design(), 3, True)
    try:
        packet, _ = export_native(model)
        assert PhysicalVolumeAudit(model, packet).check()["passed"]
        B, D, H = surface_blocks(model, packet)
        assert block_pair(packet, B, D, H)["passed"]
        rhs = incident_rhs(model, packet, B)
        assert np.linalg.norm(rhs - packet.a["total_g"]) / np.linalg.norm(rhs) < 1e-10
        from src.solvers.fixed_phase_qualification import manufactured, coefficients
        from src.solvers.fixed_phase_audit import analytic_projections, integrate_load

        fun = manufactured(model)
        c, recovery = coefficients(model, packet, lambda x: fun(x)[0])
        a = analytic_projections(model, lambda x: fun(x)[1])
        load = (
            integrate_load(
                model,
                packet,
                lambda x: fun(x)[3],
                lambda x, side: np.cross(fun(x)[2], [0, 0, 1 if side == "top" else -1]),
            )
            + B @ a
        )
        assert (
            np.linalg.norm(packet.volume(c) + B @ a - load) / np.linalg.norm(load)
            < 1e-10
        )
        assert recovery < 1e-10
        from src.solvers.fixed_phase_comparison import local_fields
        import basix

        qp, _ = basix.make_quadrature(basix.CellType.hexahedron, 5)
        local = packet.expand(c)
        for cell in (0, 7):
            E, C, x, _ = local_fields(model, cell, local[cell], qp)
            assert np.linalg.norm(E - fun(x)[1]) / np.linalg.norm(E) < 1e-10
            assert np.linalg.norm(C - fun(x)[2]) / np.linalg.norm(C) < 1e-10
    finally:
        destroy_same_mesh_physical_action(model["bundle"])


def test_grazing_air_opposite_z_original_residual_and_fields():
    from src.solvers.feinn_fem import export_native
    from src.solvers.fixed_phase_audit import (
        surface_blocks,
        analytic_projections,
        integrate_load,
    )
    from src.solvers.fixed_phase_qualification import solve_fixture, evaluate
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )

    model = build_model(fixture_design(), 3, True)
    try:
        p, _ = export_native(model)
        B, _, _ = surface_blocks(model, p)
        cfg = model["cfg"]
        e = np.asarray(cfg.polarization_vector, complex)
        for sign in (-1, 1):
            k = np.asarray([cfg.kx, cfg.ky, sign * abs(cfg.wavevector[2])], complex)

            def electric(x):
                return np.exp(1j * (x @ k))[:, None] * e

            def curl(x):
                return np.exp(1j * (x @ k))[:, None] * 1j * np.cross(k, e)

            a = analytic_projections(model, electric)
            rhs = (
                integrate_load(
                    model,
                    p,
                    lambda x: np.zeros_like(x, dtype=complex),
                    lambda x, side: np.cross(
                        curl(x), [0, 0, 1 if side == "top" else -1]
                    ),
                )
                + B @ a
            )
            audit = {}
            c, alpha, r = solve_fixture(model, p, rhs, refinement_record=audit)
            print(sign, audit, flush=True)
            assert r <= 1e-10
            assert audit["factor_count"] == 1
            assert len(audit["original_relative_residuals"]) <= 4
            E, C = evaluate(model, p, c, model["centers"])
            for measured, expected in (
                (E, electric(model["centers"])),
                (C, curl(model["centers"])),
                (alpha, a),
            ):
                assert (
                    np.linalg.norm(measured - expected) / np.linalg.norm(expected)
                    <= 1e-4
                )
    finally:
        destroy_same_mesh_physical_action(model["bundle"])
