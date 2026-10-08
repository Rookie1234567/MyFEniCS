"""Independent one-cell Si decay calibration, never a scattering solution."""

import numpy as np


def calibrate_decay(marker):
    import basix
    from src.common.optical_material_table import load_si_optical_constants
    from src.solvers.feinn_interpolation import full_moment_element

    element = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        3,
        basix.LagrangeVariant.legendre,
    )
    full = full_moment_element(element, 60)
    points, weights = basix.make_quadrature(basix.CellType.hexahedron, 60)
    table = element.tabulate(1, points)
    h = 1.25  # Actual M5 cell; the .7nm item is NOT the scaled three-dimensional pilot.
    x = h * (points - 0.5)
    rows = []
    for wavelength in (5.0, 0.7):
        material = load_si_optical_constants(wavelength)
        k0 = 2 * np.pi / wavelength
        beta = k0 * np.sqrt(material.n**2 - np.cos(np.deg2rad(1.0)) ** 2 + 0j)
        if beta.imag < 0:
            beta = -beta
        for sign in (1, -1):
            K = np.array([k0 * np.cos(np.deg2rad(1.0)), 0.0, sign * beta])
            p = np.array([0.0, 1.0, 0.0], np.complex128)
            q, kappa = K.real, K.imag
            raw = np.exp(1j * (x @ K))[:, None] * p
            neuron = np.exp(x @ (1j * q - kappa))[:, None] * p
            curl = 1j * np.cross(K, raw)
            E_nodes = np.exp((h * (full.points - 0.5)) @ (1j * q - kappa))[:, None] * p
            coeff = full.interpolation_matrix @ (h * E_nodes).T.ravel()
            E_fe = np.einsum("ndc,d->nc", table[0], coeff) / h
            derivatives = np.einsum("andc,d->anc", table[1:4], coeff) / h**2
            curl_fe = np.c_[
                derivatives[1, :, 2] - derivatives[2, :, 1],
                derivatives[2, :, 0] - derivatives[0, :, 2],
                derivatives[0, :, 1] - derivatives[1, :, 0],
            ]

            def norm(v):
                return float(np.sqrt(np.sum(weights * np.sum(abs(v) ** 2, axis=1))))

            E_error, curl_error = (
                norm(E_fe - raw) / norm(raw),
                norm(curl_fe - curl) / norm(curl),
            )
            row = dict(
                wavelength_nm=wavelength,
                propagation_z_sign=sign,
                material=material.provenance,
                K=K,
                q_real=q,
                decay_kappa=kappa,
                beta_si_nm_inverse=beta,
                amplitude_1e_depth_nm=1 / beta.imag,
                dispersion_relative=float(
                    abs(np.dot(K, K) - k0**2 * material.epsilon)
                    / abs(k0**2 * material.epsilon)
                ),
                transverse_absolute=float(abs(np.dot(K, p))),
                raw_neuron_relative=norm(neuron - raw) / norm(raw),
                exact_curl_identity="curl(E)=i K cross E; nonconjugate K dot K/K dot p",
                FE_E_L2_relative=E_error,
                FE_H_scaled_curl_relative=curl_error,
                FE_1e_4=bool(max(E_error, curl_error) <= 1e-4),
                h_nm=h,
                degree=3,
                moment_quadrature=60,
                field_quadrature=60,
                separate_from_M5_gate=True,
                reduced_0p7_pilot=False,
                pde_solve_count=0,
            )
            rows.append(row)
            marker("local_decay_plane_wave_calibration", row)
    return dict(
        calibration_qualified=bool(
            all(
                max(
                    r["dispersion_relative"],
                    r["transverse_absolute"],
                    r["raw_neuron_relative"],
                )
                <= 1e-10
                for r in rows
            )
        ),
        rows=rows,
        finite_element_interpolation_is_separate_diagnostic=True,
        reference_solve_count=0,
        global_Maxwell_factor_count=0,
        global_Gram_factor_count=0,
        local_Maxwell_factor_count=0,
        polynomial_moment_reconstruction="qualified full_moment_element density conversion; small algebra, not a PDE factor",
        physical_model="one uniform Si cell, both z signs, not the nonseparable M5 scattering case",
    )
