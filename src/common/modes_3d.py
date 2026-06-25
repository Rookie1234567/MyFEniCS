from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config_3d import SimulationConfig3D


@dataclass(frozen=True)
class DiffractionOrder3D:
    """One transverse Floquet wavevector shared by the top and bottom ports."""

    m: int
    n: int
    alpha: complex
    gamma: complex
    beta_top: complex
    beta_bottom: complex
    top_propagating: bool
    bottom_propagating: bool
    rayleigh_warning_top: bool
    rayleigh_warning_bottom: bool


@dataclass(frozen=True)
class PortMode3D:
    """One outgoing 3D Floquet-port channel used by DtN and postprocess code."""

    side: str
    m: int
    n: int
    polarization: str
    alpha: complex
    gamma: complex
    beta: complex
    refractive_index: complex
    vertical_sign: int
    e_vector: np.ndarray
    k_vector: np.ndarray
    h_vector: np.ndarray
    electric_tangential_norm_sq: float
    power_per_unit_amplitude: float
    propagating: bool
    rayleigh_warning: bool


def positive_sqrt(value: complex) -> complex:
    """Square root branch with non-negative real/imaginary propagation sign."""

    root = np.sqrt(complex(value))
    if root.imag < -1.0e-14 or (abs(root.imag) < 1.0e-14 and root.real < 0.0):
        root = -root
    return complex(root)


def is_propagating(beta: complex) -> bool:
    return abs(complex(beta).imag) < 1.0e-9 and complex(beta).real > 1.0e-12


def near_rayleigh(beta: complex, n_medium: complex, cfg: SimulationConfig3D) -> bool:
    scale = max(abs(complex(n_medium) * cfg.k0), 1.0e-30)
    return abs(complex(beta)) / scale < cfg.diffraction_rayleigh_tol


def enumerate_diffraction_orders_3d(
    cfg: SimulationConfig3D,
    *,
    max_m_override: int | None = None,
    max_n_override: int | None = None,
) -> list[DiffractionOrder3D]:
    """Enumerate the 2D Floquet lattice orders for a 3D periodic cell."""

    if max_m_override is not None or max_n_override is not None:
        max_m = 0 if max_m_override is None else int(max_m_override)
        max_n = 0 if max_n_override is None else int(max_n_override)
    elif cfg.diffraction_zero_order_only:
        max_m = 0
        max_n = 0
    else:
        n_max = max(abs(complex(cfg.n_air)), abs(complex(cfg.substrate_index)))
        auto_max_m = int(
            np.floor((n_max * cfg.k0 + abs(cfg.kx)) * (cfg.x_max - cfg.x_min) / (2.0 * np.pi) + 1.0e-12)
        )
        auto_max_n = int(
            np.floor((n_max * cfg.k0 + abs(cfg.ky)) * (cfg.y_max - cfg.y_min) / (2.0 * np.pi) + 1.0e-12)
        )
        max_m = auto_max_m if cfg.diffraction_order_max_m is None else max(int(cfg.diffraction_order_max_m), auto_max_m)
        max_n = auto_max_n if cfg.diffraction_order_max_n is None else max(int(cfg.diffraction_order_max_n), auto_max_n)
    if max_m < 0 or max_n < 0:
        raise ValueError("diffraction_order_max_m/n must be non-negative.")

    orders: list[DiffractionOrder3D] = []
    for m in range(-int(max_m), int(max_m) + 1):
        for n in range(-int(max_n), int(max_n) + 1):
            alpha = complex(cfg.kx + 2.0 * np.pi * m / (cfg.x_max - cfg.x_min))
            gamma = complex(cfg.ky + 2.0 * np.pi * n / (cfg.y_max - cfg.y_min))
            beta_top = positive_sqrt((cfg.k0 * complex(cfg.n_air)) ** 2 - alpha**2 - gamma**2)
            beta_bottom = positive_sqrt(
                (cfg.k0 * complex(cfg.substrate_index)) ** 2 - alpha**2 - gamma**2
            )
            orders.append(
                DiffractionOrder3D(
                    m=m,
                    n=n,
                    alpha=alpha,
                    gamma=gamma,
                    beta_top=beta_top,
                    beta_bottom=beta_bottom,
                    top_propagating=is_propagating(beta_top),
                    bottom_propagating=is_propagating(beta_bottom),
                    rayleigh_warning_top=near_rayleigh(beta_top, cfg.n_air, cfg),
                    rayleigh_warning_bottom=near_rayleigh(beta_bottom, cfg.substrate_index, cfg),
                )
            )
    return orders


def polarization_basis_3d(
    alpha: complex,
    gamma: complex,
    beta: complex,
    n_medium: complex,
    vertical_sign: int,
    cfg: SimulationConfig3D,
) -> list[tuple[str, np.ndarray]]:
    """Return two unit E-polarization vectors for one 3D Floquet order."""

    kt_norm = float(np.sqrt(abs(alpha) ** 2 + abs(gamma) ** 2))
    if kt_norm < 1.0e-12 * max(abs(cfg.k0 * complex(n_medium)), 1.0):
        return [
            ("x", np.asarray((1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j), dtype=np.complex128)),
            ("y", np.asarray((0.0 + 0.0j, 1.0 + 0.0j, 0.0 + 0.0j), dtype=np.complex128)),
        ]

    s_vec = np.asarray((-gamma / kt_norm, alpha / kt_norm, 0.0 + 0.0j), dtype=np.complex128)
    kvec = np.asarray((alpha, gamma, vertical_sign * beta), dtype=np.complex128)
    direction = kvec / (cfg.k0 * complex(n_medium))
    p_vec = np.cross(direction, s_vec)
    p_norm = float(np.sqrt(np.sum(np.abs(p_vec) ** 2)))
    if p_norm <= 0.0:
        raise ValueError("Cannot build p polarization for a degenerate 3D Floquet mode.")
    return [("s", s_vec), ("p", p_vec / p_norm)]


def mode_eh_vectors(
    alpha: complex,
    gamma: complex,
    beta: complex,
    polarization: np.ndarray,
    vertical_sign: int,
    cfg: SimulationConfig3D,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return k, E, H code-unit vectors for one unit-amplitude mode."""

    kvec = np.asarray((alpha, gamma, vertical_sign * beta), dtype=np.complex128)
    e_vec = np.asarray(polarization, dtype=np.complex128)
    h_vec = np.cross(kvec, e_vec) / (cfg.k0 * complex(cfg.mu_r))
    return kvec, e_vec, h_vec


def mode_power(
    kvec: np.ndarray,
    e_vec: np.ndarray,
    cfg: SimulationConfig3D,
    outward_normal: np.ndarray,
) -> float:
    """Power carried through one unit cell by a unit-amplitude mode."""

    h_vec = np.cross(kvec, e_vec) / (cfg.k0 * complex(cfg.mu_r))
    s_vec = 0.5 * np.real(np.cross(e_vec, np.conj(h_vec)))
    density = float(np.dot(s_vec, outward_normal))
    return max(density, 0.0) * (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)


def incident_power_3d(cfg: SimulationConfig3D) -> float:
    """Power injected by the normalized incident plane wave."""

    e_vec = complex(cfg.incident_amplitude) * np.asarray(cfg.polarization_vector, dtype=np.complex128)
    h_vec = np.cross(np.asarray(cfg.wavevector, dtype=np.complex128), e_vec) / (cfg.k0 * complex(cfg.mu_r))
    s_vec = 0.5 * np.real(np.cross(e_vec, np.conj(h_vec)))
    area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    return max(float(-s_vec[2]) * area, 1.0e-30)


def outgoing_port_modes_3d(cfg: SimulationConfig3D) -> list[PortMode3D]:
    """Select outgoing top/bottom DtN modes according to the Stage-4 policy."""

    policy = cfg.stage4_dtn_order_policy.lower()
    if policy == "zero_order":
        orders = enumerate_diffraction_orders_3d(cfg, max_m_override=0, max_n_override=0)
    elif policy in {"auto_propagating", "manual"}:
        n_max = max(abs(complex(cfg.n_air)), abs(complex(cfg.substrate_index)))
        auto_max_m = int(
            np.floor((n_max * cfg.k0 + abs(cfg.kx)) * (cfg.x_max - cfg.x_min) / (2.0 * np.pi) + 1.0e-12)
        )
        auto_max_n = int(
            np.floor((n_max * cfg.k0 + abs(cfg.ky)) * (cfg.y_max - cfg.y_min) / (2.0 * np.pi) + 1.0e-12)
        )
        max_m = auto_max_m if cfg.diffraction_order_max_m is None else max(int(cfg.diffraction_order_max_m), auto_max_m)
        max_n = auto_max_n if cfg.diffraction_order_max_n is None else max(int(cfg.diffraction_order_max_n), auto_max_n)
        orders = enumerate_diffraction_orders_3d(cfg, max_m_override=max_m, max_n_override=max_n)
    else:
        raise ValueError("stage4_dtn_order_policy must be 'auto_propagating', 'zero_order', or 'manual'.")

    modes: list[PortMode3D] = []
    side_specs = (
        ("top", cfg.n_air, np.asarray((0.0, 0.0, 1.0), dtype=np.float64), 1),
        ("bottom", cfg.substrate_index, np.asarray((0.0, 0.0, -1.0), dtype=np.float64), -1),
    )
    for side, n_medium, outward_normal, vertical_sign in side_specs:
        for order in orders:
            beta = order.beta_top if side == "top" else order.beta_bottom
            propagating = order.top_propagating if side == "top" else order.bottom_propagating
            rayleigh_warning = order.rayleigh_warning_top if side == "top" else order.rayleigh_warning_bottom
            selected = (order.m == 0 and order.n == 0) or bool(propagating)
            if policy == "manual":
                selected = True
            if not selected:
                continue
            for pol_name, e_vec in polarization_basis_3d(
                order.alpha,
                order.gamma,
                beta,
                n_medium,
                vertical_sign,
                cfg,
            ):
                kvec, e_vec, h_vec = mode_eh_vectors(order.alpha, order.gamma, beta, e_vec, vertical_sign, cfg)
                tangential_norm_sq = float(np.real(np.vdot(e_vec[:2], e_vec[:2])))
                if tangential_norm_sq <= 1.0e-30:
                    continue
                modes.append(
                    PortMode3D(
                        side=side,
                        m=order.m,
                        n=order.n,
                        polarization=pol_name,
                        alpha=order.alpha,
                        gamma=order.gamma,
                        beta=beta,
                        refractive_index=complex(n_medium),
                        vertical_sign=vertical_sign,
                        e_vector=e_vec,
                        k_vector=kvec,
                        h_vector=h_vec,
                        electric_tangential_norm_sq=tangential_norm_sq,
                        power_per_unit_amplitude=mode_power(kvec, e_vec, cfg, outward_normal),
                        propagating=bool(propagating),
                        rayleigh_warning=bool(rayleigh_warning),
                    )
                )
    return modes
