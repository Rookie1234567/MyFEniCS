"""Independent FE witnesses for the new complete wave-moment chain.

Only local FE tabulation/postprocessing and the original MPC are rebuilt.
No reference solution, global FE matrix, Gram matrix or factor is used.
"""

from copy import deepcopy
from time import perf_counter

import numpy as np

from src.solvers.neural_wave_moments import WaveMoments, pack, unpack
from src.solvers.neural_wave_greedy import (
    atomic_npz,
    variable_projection,
    patch_inventory,
)
from src.solvers.neural_wave_subspace import WaveSubspace


def relative(x, y):
    return float(np.linalg.norm(x - y) / max(np.linalg.norm(y), 1e-30))


def build_moment_witness(model, quadrature):
    from src.solvers.feinn_fem import physical_config
    from src.solvers.feinn_interpolation import full_space, build_full_moments
    from src.constraints.floquet_3d import build_double_floquet_mpc

    cfg, _ = physical_config(model)
    _, data, space, centers, _, _, _ = full_space(model)
    floquet = build_double_floquet_mpc(space, data, cfg)
    packet, witness = build_full_moments(
        space, floquet.mpc, quadrature, model["geometry"]["cells"]
    )
    return cfg, data, space, floquet, packet, witness, centers


def qualify(model, action, packet, artifact, marker):
    from dolfinx import fem
    from src.solvers.feinn_interpolation import complete_interpolation_check
    from src.solvers.neural_trace import moment_packet_values

    start = perf_counter()
    marker("building_independent_high_moment_witness", dict(quadrature=60))
    _, _, space, floquet, high, witness, _ = build_moment_witness(model, 60)
    if not np.array_equal(high["master_native_rows"], action.a["masters"]):
        raise ValueError("ORIGINAL_NATIVE_MASTER_ORDER_CHANGED")
    for key in (
        "master_native_rows",
        "native_cell_dofs",
        "owner_rows",
        "orientation_ids",
    ):
        if not np.array_equal(packet[key], high[key]):
            raise ValueError("ORIGINAL_COMPLETE_MOMENT_IDENTITY_CHANGED: " + key)
    full = complete_interpolation_check(high, space, witness, floquet.mpc)
    if full["status"] != "PASS":
        raise ValueError("FULL_HIGH_MOMENT_MAPPING_NOT_QUALIFIED")
    atomic_npz(artifact / "moments_q60.npz", **high)
    low_map, high_map = WaveMoments(packet, 8), WaveMoments(high, 8)
    rng = np.random.default_rng(4213002)
    patches = [
        patch_inventory(model["geometry"], level)[
            len(patch_inventory(model["geometry"], level)) // 2
        ]
        for level in range(3)
    ]
    k0 = 2 * np.pi / model["wavelength_nm"]
    rows = []
    for number, patch in enumerate(patches):
        # Includes the largest admissible Cartesian phase span, all components,
        # nonzero imaginary amplitudes, and actual vertex-star support.
        q = k0 * np.array([[4.0, -4.0, 4.0], [1.27, 0.33, -0.56]])
        p = rng.normal(size=(2, 3)) + 1j * rng.normal(size=(2, 3))

        def raw(x):
            return patch.window(x)[:, None] * (
                np.exp(1j * (x - patch.center) @ q.T) @ p
            )

        c = low_map.forward(patch, q, p)
        h = high_map.forward(patch, q, p)
        direct = moment_packet_values(packet, raw)
        independent = fem.Function(witness)
        independent.interpolate(lambda x: raw(x.T).T)
        original = independent.x.array[high["master_native_rows"]]
        mpc_field = fem.Function(floquet.mpc.function_space)
        mpc_field.x.array[:] = 0
        mpc_field.x.array[high["master_native_rows"]] = h
        floquet.mpc.backsubstitution(mpc_field)
        coeff, offsets = floquet.mpc.coefficients()
        defects = [
            mpc_field.x.array[s]
            - np.dot(
                coeff[offsets[s] : offsets[s + 1]],
                mpc_field.x.array[floquet.mpc.masters.links(int(s))],
            )
            for s in floquet.mpc.slaves
        ]
        family = {}
        for name in ("edge", "face", "interior"):
            selected = packet["owner_rows"][:, packet[name + "_positions"]].ravel()
            selected = selected[selected >= 0]
            family[name] = dict(
                count=len(selected),
                norm=float(np.linalg.norm(c[selected])),
                full_mapping_relative=relative(c[selected], direct[selected]),
                higher_rule_relative=relative(c[selected], h[selected]),
            )
        cot = rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
        gq, gp = low_map.vjp(patch, q, p, cot)
        theta, grad = pack(q, p), pack(gq, gp)
        fd = []
        for _ in range(3):
            v = rng.normal(size=len(theta))
            v /= np.linalg.norm(v)
            exact = float(grad @ v)
            for step in (1e-4, 1e-5, 1e-6):
                cp = low_map.forward(patch, *unpack(theta + step * v))
                cm = low_map.forward(patch, *unpack(theta - step * v))
                finite = float(np.vdot(cot, cp - cm).real / (2 * step))
                fd.append(
                    dict(
                        step=step,
                        finite=finite,
                        analytic=exact,
                        relative=abs(finite - exact) / max(abs(exact), 1e-12),
                    )
                )
        field_one = WaveMoments(packet, 1).forward(patch, q, p)
        row = dict(
            patch=number,
            batch1_8_relative=relative(field_one, c),
            sparse_dense_relative=relative(c, direct),
            independent_FE_relative=relative(h, original),
            quadrature30_60_relative=relative(c, h),
            families=family,
            mpc_expansion_relative=float(
                np.linalg.norm(defects) / np.linalg.norm(mpc_field.x.array)
            ),
            nonzero_real_direction_FD=fd,
        )
        rows.append(row)
        marker("complete_wave_mapping_witness", row)
    # Original full action and its adjoint, not a trace or reduced-space action.
    spaceQR = WaveSubspace(action, 8)
    q = k0 * np.array([[1.13, 0.32, -0.71]])
    for patch in patches[:2]:
        spaceQR.add(low_map.forward(patch, q, np.array([[0.2 + 0.3j, 1.0, -0.4j]])))
    value = variable_projection(action, spaceQR, low_map, patches[-1], q, gradient=True)
    v = rng.normal(size=q.shape)
    v /= np.linalg.norm(v)
    fd_score = []
    for step in (1e-4, 1e-5, 1e-6):
        plus = variable_projection(
            action, spaceQR, low_map, patches[-1], q + step * v, gradient=False
        )[0]
        minus = variable_projection(
            action, spaceQR, low_map, patches[-1], q - step * v, gradient=False
        )[0]
        finite = (plus - minus) / (2 * step * action.bnorm**2)
        exact = float(np.sum(value[-1] * v))
        fd_score.append(
            dict(
                step=step,
                finite=finite,
                analytic=exact,
                relative=abs(finite - exact) / max(abs(exact), 1e-12),
            )
        )
    passed = full["status"] == "PASS" and all(
        max(
            row["batch1_8_relative"],
            row["sparse_dense_relative"],
            row["independent_FE_relative"],
            row["mpc_expansion_relative"],
        )
        <= 1e-10
        and row["quadrature30_60_relative"] <= 1e-8
        and max(item["relative"] for item in row["nonzero_real_direction_FD"]) <= 1e-5
        for row in rows
    )
    passed &= min(item["relative"] for item in fd_score) <= 1e-5
    return dict(
        implementation_qualified=bool(passed),
        full_polynomial_mapping=full,
        wave_witnesses=rows,
        native_score_gradient=fd_score,
        small_R_rank_audit=spaceQR.rank_audit(),
        elapsed_seconds=perf_counter() - start,
        reference_loaded=False,
        Gram_or_Maxwell_factor_count=0,
        interpolation_degree=30,
        independent_interpolation_degree=60,
    )


def analytic_calibration(model, wavelength, artifact, marker):
    """Air plane and physical flat-interface fields; no PDE solve or labels."""
    import basix
    import ufl
    from dolfinx import fem
    from src.common.optical_material_table import load_si_optical_constants
    from src.solvers.neural_trace import moment_packet_values

    config = deepcopy(model)
    config["wavelength_nm"] = wavelength
    material = load_si_optical_constants(wavelength)
    config["materials"]["si_n"] = [material.n.real, material.n.imag]
    cfg, data, space, floquet, packet, witness, _ = build_moment_witness(config, 60)
    k0 = cfg.k0
    beta = k0 * np.sin(np.deg2rad(1.0))
    kx = k0 * np.cos(np.deg2rad(1.0))
    substrate_beta = np.sqrt(complex(k0 * k0 * material.n**2 - kx * kx))
    if substrate_beta.imag < 0:
        substrate_beta = -substrate_beta
    reflection = (beta - substrate_beta) / (beta + substrate_beta)
    transmission = 1 + reflection
    quad, weights = basix.make_quadrature(basix.CellType.hexahedron, 30)
    cells = np.arange(space.mesh.topology.index_map(3).size_local, dtype=np.int32)
    origin, jac = packet["origins"], packet["jacobians"]
    points = origin[:, None, :] + np.einsum("pj,cij->cpi", quad, jac)
    volume_weights = np.linalg.det(jac)[:, None] * weights
    rows = {}
    for name in ("air_plane", "flat_interface"):

        def fields(x):
            down = np.exp(-1j * beta * x[:, 2])
            ey = down.copy()
            derivative_z = -1j * beta * down
            if name == "flat_interface":
                up = reflection * np.exp(1j * beta * x[:, 2])
                below = transmission * np.exp(-1j * substrate_beta * x[:, 2])
                ey = np.where(x[:, 2] >= 0, down + up, below)
                derivative_z = np.where(
                    x[:, 2] >= 0,
                    -1j * beta * down + 1j * beta * up,
                    -1j * substrate_beta * below,
                )
            phase = np.exp(1j * kx * x[:, 0])
            E = np.zeros((len(x), 3), complex)
            E[:, 1] = phase * ey
            curl = np.column_stack(
                (-phase * derivative_z, np.zeros(len(x)), 1j * kx * phase * ey)
            )
            return E, curl

        c = moment_packet_values(packet, lambda x: fields(x)[0])
        E = fem.Function(floquet.mpc.function_space)
        E.x.array[:] = 0
        E.x.array[packet["master_native_rows"]] = c
        floquet.mpc.backsubstitution(E)
        actual = (
            fem.Expression(E, quad)
            .eval(data.mesh, cells)
            .reshape(len(cells), len(quad), 3)
        )
        curl = (
            fem.Expression(ufl.curl(E), quad)
            .eval(data.mesh, cells)
            .reshape(actual.shape)
        )
        rawE, rawCurl = fields(points.reshape(-1, 3))
        rawE, rawCurl = rawE.reshape(actual.shape), rawCurl.reshape(actual.shape)

        def norm(v):
            return float(np.sqrt(np.sum(volume_weights * np.sum(abs(v) ** 2, axis=2))))

        errorE, errorCurl = (
            norm(actual - rawE) / norm(rawE),
            norm(curl - rawCurl) / norm(rawCurl),
        )
        rows[name] = dict(
            raw_exponential_representation_error=0.0,
            raw_interface_assembly="independent Fresnel s; continuous E, derivative follows medium",
            finite_element_L2_relative=errorE,
            finite_element_H_scaled_curl_relative=errorCurl,
            FE_interpolation_accuracy_1e_4=bool(max(errorE, errorCurl) <= 1e-4),
            interpretation="diagnostic only; this is not the nonseparable M5 solve",
        )
        marker(
            "analytic_calibration",
            dict(wavelength_nm=wavelength, field=name, **rows[name]),
        )
    return dict(
        wavelength_nm=wavelength,
        material=material.provenance,
        cells=len(cells),
        degree=3,
        h_nm=model["geometry"]["step_nm"],
        fields=rows,
        reference_solve_count=0,
        analytic_only=True,
        nonseparable_M5_numerical_gate=False,
    )
