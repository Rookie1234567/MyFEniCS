"""Physical Poynting gate for both air directions, no real B solve replay."""

import json
import os
from pathlib import Path
import numpy as np


def test_opposite_z_air_physical_flux_all_modes():
    from src.geometry.fixed_phase_plan import fixture_design
    from src.solvers.fixed_phase_fem import build_model
    from src.solvers.feinn_fem import export_native
    from src.solvers.fixed_phase_audit import (
        analytic_projections,
        integrate_load,
        surface_blocks,
    )
    from src.solvers.fixed_phase_qualification import solve_fixture
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )
    from src.solvers.dtn_port_3d import (
        _mode_power_at_boundary,
        _mode_carries_outward_power,
    )
    from src.common.modes_3d import incident_power_3d

    model = build_model(fixture_design(), 3, True)
    rows = []
    try:
        p, _ = export_native(model)
        B, _, _ = surface_blocks(model, p)
        cfg = model["cfg"]
        modes = model["bundle"]["modes"]
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
            _, actual, residual = solve_fixture(model, p, rhs)
            incoming_side = "top" if sign == -1 else "bottom"
            outgoing_side = "bottom" if sign == -1 else "top"
            incoming = np.zeros(len(modes), complex)
            exact_out = np.zeros_like(incoming)
            for j, m in enumerate(modes):
                if m.m == 0 and m.n == 0:
                    z = cfg.physical_z_max if m.side == "top" else cfg.physical_z_min
                    projection = (
                        np.vdot(np.asarray(m.e_vector[:2]), e[:2])
                        / np.vdot(m.e_vector[:2], m.e_vector[:2]).real
                    )
                    value = projection * np.exp(1j * (k[2] - m.k_vector[2]) * z)
                    if m.side == incoming_side:
                        incoming[j] = value
                    if m.side == outgoing_side:
                        exact_out[j] = value
            outgoing = actual - incoming
            port = []
            direct = []
            exact = []
            for j, m in enumerate(modes):
                z = cfg.physical_z_max if m.side == "top" else cfg.physical_z_min

                def flux(alpha):
                    E = alpha * np.exp(1j * m.k_vector[2] * z) * np.asarray(m.e_vector)
                    H = np.cross(m.k_vector, E) / (cfg.k0 * cfg.mu_r)
                    return max(
                        float(
                            0.5
                            * np.cross(E, H.conj())[2].real
                            * (1 if m.side == "top" else -1)
                            * cfg.period_x
                            * cfg.period_y
                            / incident_power_3d(cfg)
                        ),
                        0,
                    )

                direct.append(flux(outgoing[j]))
                exact.append(flux(exact_out[j]))
                port.append(
                    _mode_power_at_boundary(m, cfg, outgoing[j])
                    / incident_power_3d(cfg)
                    if _mode_carries_outward_power(m)
                    else 0.0
                )
            direct = np.asarray(direct)
            exact = np.asarray(exact)
            port = np.asarray(port)
            reflected = float(
                sum(direct[j] for j, m in enumerate(modes) if m.side == incoming_side)
            )
            transmitted = float(
                sum(direct[j] for j, m in enumerate(modes) if m.side == outgoing_side)
            )
            row = dict(
                z_sign=sign,
                incoming_side=incoming_side,
                outgoing_side=outgoing_side,
                channels=len(modes),
                original_residual=residual,
                independent_Poynting_vs_port_max_absolute=float(
                    max(abs(direct - port))
                ),
                all_mode_vs_analytic_max_absolute=float(max(abs(direct - exact))),
                reflected=reflected,
                transmitted=transmitted,
                energy_closure=abs(sum(direct) - 1),
                per_mode_physical_power=direct.tolist(),
                per_mode_analytic_power=exact.tolist(),
            )
            rows.append(row)
            assert residual <= 1e-10
            assert row["independent_Poynting_vs_port_max_absolute"] <= 1e-12
            assert row["all_mode_vs_analytic_max_absolute"] <= 1e-6
            assert (
                reflected <= 1e-5
                and abs(transmitted - 1) <= 1e-5
                and row["energy_closure"] <= 1e-5
            )
    finally:
        destroy_same_mesh_physical_action(model["bundle"])
    destination = Path(
        os.environ.get(
            "TASK42EXTRA_AIR_FLUX_RECORD", "tmp/task42extra/v20/air_physical_flux.json"
        )
    )
    assert not destination.exists()
    destination.write_text(
        json.dumps(
            dict(
                status="PASS",
                rows=rows,
                source_scope="new independent targeted qualification, not a B replay",
                no_Gram_or_NN=True,
                fixture_global_LU_count=2,
            ),
            indent=2,
        )
        + "\n"
    )
