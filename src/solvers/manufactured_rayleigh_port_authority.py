"""Independent manufactured authority for the Stage-4 Rayleigh-port convention.

This module deliberately does not import the production DtN implementation.
It evaluates closed-form Maxwell plane waves and their finite-plane
projections with a small tensor Gauss rule.  The resulting authority can
therefore distinguish a shared implementation convention from an independent
physics check without launching a PDE solve.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


AUTHORITY_TOLERANCE = 5.0e-12


@dataclass(frozen=True)
class ManufacturedRayleighMode:
    """One analytic outgoing or incoming Rayleigh mode."""

    side: str
    direction: str
    polarization: str
    alpha: complex
    gamma: complex
    beta: complex
    k0: float
    epsilon_r: complex
    mu_r: complex
    vertical_sign: int
    outward_normal: np.ndarray
    k_vector: np.ndarray
    e_vector: np.ndarray
    h_vector: np.ndarray


def _complex_pair(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _finite_complex(value: complex) -> bool:
    number = complex(value)
    return bool(np.isfinite(number.real) and np.isfinite(number.imag))


def manufactured_rayleigh_mode(
    *,
    side: str,
    direction: str,
    polarization: str,
    alpha: complex,
    gamma: complex,
    beta: complex,
    k0: float,
    epsilon_r: complex = 1.0 + 0.0j,
    mu_r: complex = 1.0 + 0.0j,
) -> ManufacturedRayleighMode:
    """Construct a source-free analytic Rayleigh mode.

    ``beta`` uses the branch with non-negative real/imaginary part.  The
    vertical sign is then selected solely by the finite port side and by
    whether the mode is outgoing or incoming.
    """

    if side not in {"top", "bottom"}:
        raise ValueError("side must be 'top' or 'bottom'")
    if direction not in {"outgoing", "incoming"}:
        raise ValueError("direction must be 'outgoing' or 'incoming'")
    if polarization not in {"s", "p"}:
        raise ValueError("polarization must be 's' or 'p'")
    if not np.isfinite(k0) or k0 <= 0.0:
        raise ValueError("k0 must be finite and positive")
    if not _finite_complex(epsilon_r) or abs(complex(epsilon_r)) <= 0.0:
        raise ValueError("epsilon_r must be finite and nonzero")
    if not _finite_complex(mu_r) or abs(complex(mu_r)) <= 0.0:
        raise ValueError("mu_r must be finite and nonzero")

    outward_sign = 1 if side == "top" else -1
    vertical_sign = (
        outward_sign if direction == "outgoing" else -outward_sign
    )
    k_vector = np.asarray(
        (complex(alpha), complex(gamma), vertical_sign * complex(beta)),
        dtype=np.complex128,
    )
    transverse_norm = float(
        np.sqrt(abs(complex(alpha)) ** 2 + abs(complex(gamma)) ** 2)
    )
    if transverse_norm <= 1.0e-14:
        s_vector = np.asarray(
            (1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j),
            dtype=np.complex128,
        )
    else:
        s_vector = np.asarray(
            (
                -complex(gamma) / transverse_norm,
                complex(alpha) / transverse_norm,
                0.0 + 0.0j,
            ),
            dtype=np.complex128,
        )
    if polarization == "s":
        e_vector = s_vector
    else:
        p_vector = np.cross(k_vector, s_vector)
        p_norm = float(np.sqrt(np.sum(np.abs(p_vector) ** 2)))
        if p_norm <= 0.0:
            raise ValueError("degenerate manufactured p polarization")
        e_vector = p_vector / p_norm
    h_vector = (
        np.cross(k_vector, e_vector)
        / (float(k0) * complex(mu_r))
    )
    outward_normal = np.asarray(
        (0.0, 0.0, float(outward_sign)),
        dtype=np.float64,
    )
    return ManufacturedRayleighMode(
        side=side,
        direction=direction,
        polarization=polarization,
        alpha=complex(alpha),
        gamma=complex(gamma),
        beta=complex(beta),
        k0=float(k0),
        epsilon_r=complex(epsilon_r),
        mu_r=complex(mu_r),
        vertical_sign=vertical_sign,
        outward_normal=outward_normal,
        k_vector=k_vector,
        e_vector=np.asarray(e_vector, dtype=np.complex128),
        h_vector=np.asarray(h_vector, dtype=np.complex128),
    )


def source_free_maxwell_identity_audit(
    mode: ManufacturedRayleighMode,
) -> dict[str, Any]:
    """Audit the source-free identities for one manufactured mode.

    With ``exp(+i k dot x) exp(-i omega t)``, the code-unit curl identities
    are ``k cross E = k0 mu H`` and ``k cross H = -k0 epsilon E``.  Bilinear
    dot products are intentional because Hermitian products are incorrect for
    complex evanescent wavevectors.
    """

    k_vector = np.asarray(mode.k_vector, dtype=np.complex128)
    e_vector = np.asarray(mode.e_vector, dtype=np.complex128)
    h_vector = np.asarray(mode.h_vector, dtype=np.complex128)
    k_norm = float(np.linalg.norm(k_vector))
    e_norm = float(np.linalg.norm(e_vector))
    h_norm = float(np.linalg.norm(h_vector))
    k_cross_e = np.cross(k_vector, e_vector)
    k_cross_h = np.cross(k_vector, h_vector)
    dispersion_target = (
        mode.k0**2 * mode.epsilon_r * mode.mu_r
    )
    residuals = {
        "dispersion": float(
            abs(np.dot(k_vector, k_vector) - dispersion_target)
            / max(
                float(np.sum(np.abs(k_vector) ** 2)),
                abs(dispersion_target),
                1.0e-30,
            )
        ),
        "k_dot_e": float(
            abs(np.dot(k_vector, e_vector))
            / max(k_norm * e_norm, 1.0e-30)
        ),
        "k_dot_h": float(
            abs(np.dot(k_vector, h_vector))
            / max(k_norm * h_norm, 1.0e-30)
        ),
        "faraday": float(
            np.linalg.norm(
                k_cross_e - mode.k0 * mode.mu_r * h_vector
            )
            / max(
                float(np.linalg.norm(k_cross_e)),
                abs(mode.k0 * mode.mu_r) * h_norm,
                1.0e-30,
            )
        ),
        "ampere": float(
            np.linalg.norm(
                k_cross_h + mode.k0 * mode.epsilon_r * e_vector
            )
            / max(
                float(np.linalg.norm(k_cross_h)),
                abs(mode.k0 * mode.epsilon_r) * e_norm,
                1.0e-30,
            )
        ),
    }
    checks = {
        "all_residuals_finite": all(
            np.isfinite(value) for value in residuals.values()
        ),
        "dispersion_identity": (
            residuals["dispersion"] <= AUTHORITY_TOLERANCE
        ),
        "electric_transversality": (
            residuals["k_dot_e"] <= AUTHORITY_TOLERANCE
        ),
        "magnetic_transversality": (
            residuals["k_dot_h"] <= AUTHORITY_TOLERANCE
        ),
        "faraday_identity_k_cross_e_eq_k0_mu_h": (
            residuals["faraday"] <= AUTHORITY_TOLERANCE
        ),
        "ampere_identity_k_cross_h_eq_minus_k0_epsilon_e": (
            residuals["ampere"] <= AUTHORITY_TOLERANCE
        ),
    }
    return {
        "phasor_convention": (
            "exp(+i*k dot x) with implicit exp(-i*omega*t)"
        ),
        "epsilon_r": _complex_pair(mode.epsilon_r),
        "mu_r": _complex_pair(mode.mu_r),
        "scale_normalized_residuals": residuals,
        "maximum_scale_normalized_residual": max(
            residuals.values()
        ),
        "checks": checks,
        "pass": all(checks.values()),
    }


def rayleigh_phase(
    mode: ManufacturedRayleighMode,
    x: np.ndarray,
    y: np.ndarray,
    z: float,
    *,
    reference_z: float | None = None,
) -> np.ndarray:
    """Return the global-z or boundary-referenced analytic phase."""

    z_coordinate = float(z)
    if reference_z is not None:
        z_coordinate -= float(reference_z)
    return np.exp(
        1j
        * (
            mode.alpha * np.asarray(x)
            + mode.gamma * np.asarray(y)
            + mode.k_vector[2] * z_coordinate
        )
    )


def _tensor_gauss_plane(
    *,
    lx: float,
    ly: float,
    quadrature_points: int = 12,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not np.isfinite(lx) or not np.isfinite(ly) or lx <= 0.0 or ly <= 0.0:
        raise ValueError("plane lengths must be finite and positive")
    if quadrature_points < 2:
        raise ValueError("quadrature_points must be at least two")
    points, weights = np.polynomial.legendre.leggauss(
        int(quadrature_points)
    )
    x = 0.5 * float(lx) * (points + 1.0)
    y = 0.5 * float(ly) * (points + 1.0)
    wx = 0.5 * float(lx) * weights
    wy = 0.5 * float(ly) * weights
    xx, yy = np.meshgrid(x, y, indexing="ij")
    plane_weights = np.outer(wx, wy)
    return xx, yy, plane_weights


def _plane_inner(
    left: np.ndarray,
    right: np.ndarray,
    weights: np.ndarray,
) -> complex:
    """Numerically assemble ``integral left dot conj(right)``."""

    integrand = np.sum(
        np.asarray(left)[..., :2] * np.conj(np.asarray(right)[..., :2]),
        axis=-1,
    )
    return complex(np.sum(np.asarray(weights) * integrand))


def numerical_rayleigh_projection(
    mode: ManufacturedRayleighMode,
    *,
    global_amplitude: complex,
    z: float,
    lx: float,
    ly: float,
    reference_z: float | None,
    quadrature_points: int = 12,
) -> tuple[complex, float]:
    """Project a manufactured field onto one global or local port basis."""

    xx, yy, weights = _tensor_gauss_plane(
        lx=lx,
        ly=ly,
        quadrature_points=quadrature_points,
    )
    field_phase = rayleigh_phase(mode, xx, yy, z)
    reference_phase = rayleigh_phase(
        mode,
        xx,
        yy,
        z,
        reference_z=reference_z,
    )
    field = (
        complex(global_amplitude)
        * field_phase[..., None]
        * mode.e_vector
    )
    reference = reference_phase[..., None] * mode.e_vector
    denominator = float(np.real(_plane_inner(reference, reference, weights)))
    if not np.isfinite(denominator) or denominator <= 0.0:
        raise FloatingPointError(
            "manufactured projection denominator is non-finite or non-positive"
        )
    coefficient = _plane_inner(field, reference, weights) / denominator
    if not _finite_complex(coefficient):
        raise FloatingPointError(
            "manufactured projection produced a non-finite coefficient"
        )
    return complex(coefficient), denominator


def numerical_outward_power(
    mode: ManufacturedRayleighMode,
    *,
    global_amplitude: complex,
    z: float,
    lx: float,
    ly: float,
    quadrature_points: int = 12,
) -> float:
    """Numerically integrate signed outward real-Poynting power."""

    xx, yy, weights = _tensor_gauss_plane(
        lx=lx,
        ly=ly,
        quadrature_points=quadrature_points,
    )
    phase = rayleigh_phase(mode, xx, yy, z)
    e_field = (
        complex(global_amplitude) * phase[..., None] * mode.e_vector
    )
    h_field = (
        complex(global_amplitude) * phase[..., None] * mode.h_vector
    )
    poynting = 0.5 * np.real(
        np.cross(e_field, np.conj(h_field))
    )
    density = np.sum(poynting * mode.outward_normal, axis=-1)
    power = float(np.sum(weights * density))
    if not np.isfinite(power):
        raise FloatingPointError(
            "manufactured power integral is non-finite"
        )
    return power


def _relative_error(actual: complex | float, expected: complex | float) -> float:
    return float(
        abs(complex(actual) - complex(expected))
        / max(abs(complex(expected)), 1.0e-30)
    )


def _propagating_case(
    *,
    side: str,
    polarization: str,
    alpha: float,
    gamma: float,
    beta: float,
    k0: float,
    lx: float,
    ly: float,
    amplitude: complex,
) -> dict[str, Any]:
    mode = manufactured_rayleigh_mode(
        side=side,
        direction="outgoing",
        polarization=polarization,
        alpha=alpha,
        gamma=gamma,
        beta=beta,
        k0=k0,
    )
    incoming = manufactured_rayleigh_mode(
        side=side,
        direction="incoming",
        polarization=polarization,
        alpha=alpha,
        gamma=gamma,
        beta=beta,
        k0=k0,
    )
    if side == "top":
        z1, z2 = 0.75, 4.25
    else:
        z1, z2 = -0.75, -4.25

    global_1, denominator_1 = numerical_rayleigh_projection(
        mode,
        global_amplitude=amplitude,
        z=z1,
        lx=lx,
        ly=ly,
        reference_z=None,
    )
    global_2, denominator_2 = numerical_rayleigh_projection(
        mode,
        global_amplitude=amplitude,
        z=z2,
        lx=lx,
        ly=ly,
        reference_z=None,
    )
    local_1, local_denominator_1 = numerical_rayleigh_projection(
        mode,
        global_amplitude=amplitude,
        z=z1,
        lx=lx,
        ly=ly,
        reference_z=z1,
    )
    local_2, local_denominator_2 = numerical_rayleigh_projection(
        mode,
        global_amplitude=amplitude,
        z=z2,
        lx=lx,
        ly=ly,
        reference_z=z2,
    )
    expected_ratio = complex(
        np.exp(1j * mode.k_vector[2] * (z2 - z1))
    )
    expected_local_1 = complex(
        amplitude * np.exp(1j * mode.k_vector[2] * z1)
    )
    expected_local_2 = complex(
        amplitude * np.exp(1j * mode.k_vector[2] * z2)
    )
    observed_ratio = complex(local_2 / local_1)
    power_1 = numerical_outward_power(
        mode,
        global_amplitude=amplitude,
        z=z1,
        lx=lx,
        ly=ly,
    )
    power_2 = numerical_outward_power(
        mode,
        global_amplitude=amplitude,
        z=z2,
        lx=lx,
        ly=ly,
    )
    incoming_power = numerical_outward_power(
        incoming,
        global_amplitude=amplitude,
        z=z1,
        lx=lx,
        ly=ly,
    )
    analytic_denominator = float(
        lx
        * ly
        * np.real(np.vdot(mode.e_vector[:2], mode.e_vector[:2]))
    )
    analytic_power = float(
        0.5
        * abs(amplitude) ** 2
        * np.dot(
            np.real(np.cross(mode.e_vector, np.conj(mode.h_vector))),
            mode.outward_normal,
        )
        * lx
        * ly
    )
    maxwell = source_free_maxwell_identity_audit(mode)
    errors = {
        "global_projection_plane_1_relative": _relative_error(
            global_1,
            amplitude,
        ),
        "global_projection_plane_2_relative": _relative_error(
            global_2,
            amplitude,
        ),
        "two_plane_phase_ratio_relative": _relative_error(
            observed_ratio,
            expected_ratio,
        ),
        "boundary_projection_plane_1_relative": _relative_error(
            local_1,
            expected_local_1,
        ),
        "boundary_projection_plane_2_relative": _relative_error(
            local_2,
            expected_local_2,
        ),
        "power_invariance_relative": _relative_error(power_2, power_1),
        "power_normalization_relative": _relative_error(
            power_1,
            analytic_power,
        ),
        "global_denominator_analytic_relative": max(
            _relative_error(denominator_1, analytic_denominator),
            _relative_error(denominator_2, analytic_denominator),
        ),
        "local_denominator_analytic_relative": max(
            _relative_error(local_denominator_1, analytic_denominator),
            _relative_error(local_denominator_2, analytic_denominator),
        ),
        "global_denominator_invariance_relative": _relative_error(
            denominator_2,
            denominator_1,
        ),
        "local_denominator_invariance_relative": _relative_error(
            local_denominator_2,
            local_denominator_1,
        ),
    }
    checks = {
        "outgoing_vertical_sign_matches_port": (
            mode.vertical_sign == (1 if side == "top" else -1)
        ),
        "outgoing_kz_points_outward": (
            float(np.real(mode.k_vector[2]))
            * float(mode.outward_normal[2])
            > 0.0
        ),
        "outgoing_power_is_positive": power_1 > 0.0,
        "incoming_power_is_negative": incoming_power < 0.0,
        "global_projection_recovers_plane_independent_amplitude": (
            max(
                errors["global_projection_plane_1_relative"],
                errors["global_projection_plane_2_relative"],
            )
            <= AUTHORITY_TOLERANCE
        ),
        "two_plane_phase_propagation_matches_exp_i_kz_dz": (
            max(
                errors["two_plane_phase_ratio_relative"],
                errors["boundary_projection_plane_1_relative"],
                errors["boundary_projection_plane_2_relative"],
            )
            <= AUTHORITY_TOLERANCE
        ),
        "power_is_reference_plane_invariant": (
            errors["power_invariance_relative"]
            <= AUTHORITY_TOLERANCE
        ),
        "power_normalization_matches_analytic_poynting_flux": (
            errors["power_normalization_relative"]
            <= AUTHORITY_TOLERANCE
        ),
        "projection_normalization_matches_analytic_area_norm": (
            max(
                errors["global_denominator_analytic_relative"],
                errors["local_denominator_analytic_relative"],
                errors["global_denominator_invariance_relative"],
                errors["local_denominator_invariance_relative"],
            )
            <= AUTHORITY_TOLERANCE
        ),
    }
    return {
        "side": side,
        "polarization": polarization,
        "direction": "outgoing",
        "vertical_sign": mode.vertical_sign,
        "outward_normal": mode.outward_normal.tolist(),
        "k_vector": [_complex_pair(value) for value in mode.k_vector],
        "e_vector": [_complex_pair(value) for value in mode.e_vector],
        "h_vector": [_complex_pair(value) for value in mode.h_vector],
        "global_amplitude": _complex_pair(amplitude),
        "z_planes": [z1, z2],
        "expected_boundary_amplitude_ratio": _complex_pair(expected_ratio),
        "assembled_boundary_amplitude_ratio": _complex_pair(observed_ratio),
        "assembled_global_projections": [
            _complex_pair(global_1),
            _complex_pair(global_2),
        ],
        "assembled_boundary_projections": [
            _complex_pair(local_1),
            _complex_pair(local_2),
        ],
        "outgoing_power_at_planes": [power_1, power_2],
        "analytic_outgoing_power": analytic_power,
        "analytic_projection_denominator": analytic_denominator,
        "incoming_power_at_plane_1": incoming_power,
        "source_free_maxwell_identities": maxwell,
        "errors": errors,
        "checks": checks,
        "pass": all(checks.values()) and maxwell["pass"],
    }


def _evanescent_case(
    *,
    side: str,
    alpha: float,
    gamma: float,
    beta: complex,
    k0: float,
    lx: float,
    ly: float,
    amplitude: complex,
) -> dict[str, Any]:
    port_z = 12.0 if side == "top" else -12.0
    mode = manufactured_rayleigh_mode(
        side=side,
        direction="outgoing",
        polarization="s",
        alpha=alpha,
        gamma=gamma,
        beta=beta,
        k0=k0,
    )
    global_projection, global_denominator = (
        numerical_rayleigh_projection(
            mode,
            global_amplitude=amplitude,
            z=port_z,
            lx=lx,
            ly=ly,
            reference_z=None,
        )
    )
    boundary_projection, boundary_denominator = (
        numerical_rayleigh_projection(
            mode,
            global_amplitude=amplitude,
            z=port_z,
            lx=lx,
            ly=ly,
            reference_z=port_z,
        )
    )
    coordinate_scale = complex(
        np.exp(1j * mode.k_vector[2] * port_z)
    )
    expected_boundary_projection = coordinate_scale * amplitude
    analytic_boundary_denominator = float(
        lx
        * ly
        * np.real(np.vdot(mode.e_vector[:2], mode.e_vector[:2]))
    )

    traction_boundary = 0.31 - 0.27j
    projection_boundary = -0.19 + 0.41j
    traction_global = coordinate_scale * traction_boundary
    projection_global = coordinate_scale * projection_boundary
    eliminated_global = (
        traction_global
        * np.conj(projection_global)
        / global_denominator
    )
    eliminated_boundary = (
        traction_boundary
        * np.conj(projection_boundary)
        / boundary_denominator
    )
    outward_power = numerical_outward_power(
        mode,
        global_amplitude=amplitude,
        z=port_z,
        lx=lx,
        ly=ly,
    )
    maxwell = source_free_maxwell_identity_audit(mode)
    errors = {
        "global_projection_relative": _relative_error(
            global_projection,
            amplitude,
        ),
        "boundary_projection_relative": _relative_error(
            boundary_projection,
            expected_boundary_projection,
        ),
        "coordinate_round_trip_relative": _relative_error(
            boundary_projection / coordinate_scale,
            amplitude,
        ),
        "denominator_coordinate_scaling_relative": _relative_error(
            global_denominator,
            abs(coordinate_scale) ** 2 * boundary_denominator,
        ),
        "boundary_denominator_analytic_relative": _relative_error(
            boundary_denominator,
            analytic_boundary_denominator,
        ),
        "eliminated_operator_relative": _relative_error(
            eliminated_global,
            eliminated_boundary,
        ),
        "absolute_outward_real_power": abs(outward_power),
    }
    checks = {
        "outgoing_evanescent_sign_matches_port": (
            mode.vertical_sign == (1 if side == "top" else -1)
        ),
        "coordinate_scale_is_finite_nonzero": (
            _finite_complex(coordinate_scale)
            and abs(coordinate_scale) > 0.0
        ),
        "global_projection_recovers_global_z_amplitude": (
            errors["global_projection_relative"] <= AUTHORITY_TOLERANCE
        ),
        "boundary_projection_equals_s_times_global_amplitude": (
            errors["boundary_projection_relative"]
            <= AUTHORITY_TOLERANCE
        ),
        "boundary_to_global_coordinate_round_trip": (
            errors["coordinate_round_trip_relative"]
            <= AUTHORITY_TOLERANCE
        ),
        "global_denominator_equals_abs_s_sq_times_boundary_denominator": (
            max(
                errors["denominator_coordinate_scaling_relative"],
                errors["boundary_denominator_analytic_relative"],
            )
            <= AUTHORITY_TOLERANCE
        ),
        "eliminated_operator_is_coordinate_invariant": (
            errors["eliminated_operator_relative"]
            <= AUTHORITY_TOLERANCE
        ),
        "evanescent_mode_carries_zero_real_power": (
            errors["absolute_outward_real_power"]
            <= AUTHORITY_TOLERANCE
        ),
    }
    return {
        "side": side,
        "polarization": "s",
        "direction": "outgoing_evanescent",
        "vertical_sign": mode.vertical_sign,
        "port_z": port_z,
        "k_vector": [_complex_pair(value) for value in mode.k_vector],
        "global_amplitude": _complex_pair(amplitude),
        "coordinate_scale_s": _complex_pair(coordinate_scale),
        "abs_coordinate_scale": float(abs(coordinate_scale)),
        "assembled_global_projection": _complex_pair(global_projection),
        "assembled_boundary_projection": _complex_pair(
            boundary_projection
        ),
        "global_projection_denominator": global_denominator,
        "boundary_projection_denominator": boundary_denominator,
        "analytic_boundary_projection_denominator": (
            analytic_boundary_denominator
        ),
        "eliminated_operator_global_z": _complex_pair(
            eliminated_global
        ),
        "eliminated_operator_boundary_referenced": _complex_pair(
            eliminated_boundary
        ),
        "outward_real_power": outward_power,
        "source_free_maxwell_identities": maxwell,
        "errors": errors,
        "checks": checks,
        "pass": all(checks.values()) and maxwell["pass"],
    }


def build_manufactured_rayleigh_port_physics() -> dict[str, Any]:
    """Build the independent, deterministic manufactured physics audit."""

    lx = 50.0
    ly = 40.0
    k0 = 0.31
    alpha = 2.0 * np.pi / lx
    gamma = -2.0 * np.pi / ly
    beta = float(
        np.sqrt(k0**2 - alpha**2 - gamma**2)
    )
    amplitude = 0.37 - 0.21j
    propagating_cases = [
        _propagating_case(
            side=side,
            polarization=polarization,
            alpha=alpha,
            gamma=gamma,
            beta=beta,
            k0=k0,
            lx=lx,
            ly=ly,
            amplitude=amplitude,
        )
        for side in ("top", "bottom")
        for polarization in ("s", "p")
    ]

    evanescent_alpha = 6.0 * np.pi / lx
    evanescent_gamma = 0.0
    kappa = float(
        np.sqrt(
            evanescent_alpha**2
            + evanescent_gamma**2
            - k0**2
        )
    )
    evanescent_cases = [
        _evanescent_case(
            side=side,
            alpha=evanescent_alpha,
            gamma=evanescent_gamma,
            beta=1j * kappa,
            k0=k0,
            lx=lx,
            ly=ly,
            amplitude=amplitude,
        )
        for side in ("top", "bottom")
    ]
    all_cases = [*propagating_cases, *evanescent_cases]
    maximum_reported_error = max(
        error
        for case in all_cases
        for error in case["errors"].values()
    )
    maximum_maxwell_residual = max(
        case["source_free_maxwell_identities"][
            "maximum_scale_normalized_residual"
        ]
        for case in all_cases
    )
    checks = {
        "four_top_bottom_s_p_propagating_cases_pass": (
            len(propagating_cases) == 4
            and all(case["pass"] for case in propagating_cases)
        ),
        "two_top_bottom_evanescent_coordinate_cases_pass": (
            len(evanescent_cases) == 2
            and all(case["pass"] for case in evanescent_cases)
        ),
        "all_reported_errors_are_finite": all(
            np.isfinite(error)
            for case in all_cases
            for error in case["errors"].values()
        ),
        "maximum_reported_error_within_tolerance": (
            maximum_reported_error <= AUTHORITY_TOLERANCE
        ),
        "all_modes_satisfy_source_free_maxwell_identities": all(
            case["source_free_maxwell_identities"]["pass"]
            for case in all_cases
        ),
    }
    return {
        "schema_version": (
            "task035b.manufactured-rayleigh-port-physics.v1"
        ),
        "method": (
            "closed_form_maxwell_rayleigh_modes_plus_"
            "tensor_gauss_plane_assembly"
        ),
        "phasor_convention": (
            "exp(+i*k dot x) with implicit exp(-i*omega*t)"
        ),
        "projection_inner_product": (
            "integral E_t dot conjugate(reference_t) dS"
        ),
        "coordinate_convention": (
            "a_boundary=exp(i*kz*z_port)*a_global_z"
        ),
        "plane_lengths": {"x": lx, "y": ly},
        "quadrature_points_per_axis": 12,
        "tolerance": AUTHORITY_TOLERANCE,
        "propagating_cases": propagating_cases,
        "evanescent_cases": evanescent_cases,
        "maximum_reported_error": maximum_reported_error,
        "maximum_source_free_maxwell_residual": (
            maximum_maxwell_residual
        ),
        "checks": checks,
        "pass": all(checks.values()),
    }
