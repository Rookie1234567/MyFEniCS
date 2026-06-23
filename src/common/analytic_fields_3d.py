from __future__ import annotations

import numpy as np

from .config_3d import SimulationConfig3D


# All analytic fields in this file use exp(i k·r) with exp(-i omega t).
# Geometry and wavelength are in nm, matching SimulationConfig3D.k0.
def _positive_sqrt(value: complex) -> complex:
    root = np.sqrt(complex(value))
    if root.imag < -1.0e-14 or (abs(root.imag) < 1.0e-14 and root.real < 0.0):
        root = -root
    return complex(root)


def pml_complex_z(cfg: SimulationConfig3D, z_values: np.ndarray) -> np.ndarray:
    """Map real z positions to the complex PML coordinate z_tilde."""
    z = np.asarray(z_values, dtype=np.float64)
    zeta = z.astype(np.complex128)
    if cfg.use_pml and cfg.pml_top_thickness > 0.0:
        top = z > cfg.physical_z_max
        d_top = (z[top] - cfg.physical_z_max) / cfg.pml_top_thickness
        zeta[top] = z[top] + 1j * cfg.pml_alpha / cfg.k0 * d_top**3
    if cfg.use_pml and cfg.pml_bottom_thickness > 0.0:
        bottom = z < cfg.physical_z_min
        d_bottom = (cfg.physical_z_min - z[bottom]) / cfg.pml_bottom_thickness
        zeta[bottom] = z[bottom] - 1j * cfg.pml_alpha / cfg.k0 * d_bottom**3
    return zeta


def _phase(kx: complex, ky: complex, kz: complex, coords: np.ndarray, zeta: np.ndarray) -> np.ndarray:
    return np.exp(1j * (kx * coords[:, 0] + ky * coords[:, 1] + kz * zeta))


def _p_vector(kvec: np.ndarray, s_vector: np.ndarray, n_medium: complex, cfg: SimulationConfig3D) -> np.ndarray:
    direction = kvec / (cfg.k0 * n_medium)
    p = np.cross(direction, s_vector)
    norm = np.sqrt(np.sum(np.abs(p) ** 2))
    if norm == 0.0:
        raise ValueError("Cannot build p polarization for a zero transverse basis.")
    return p / norm


def fresnel_reference(cfg: SimulationConfig3D) -> dict[str, complex | float]:
    """Return analytic flat-interface Fresnel coefficients and power factors."""
    n1 = complex(cfg.n_air)
    n2 = complex(cfg.substrate_index)
    sin_i = np.sin(cfg.theta_rad)
    cos_i = np.cos(cfg.theta_rad)
    sin_t = n1 / n2 * sin_i
    cos_t = _positive_sqrt(1.0 - sin_t**2)

    r_s = (n1 * cos_i - n2 * cos_t) / (n1 * cos_i + n2 * cos_t)
    t_s = 2.0 * n1 * cos_i / (n1 * cos_i + n2 * cos_t)
    r_p = (n2 * cos_i - n1 * cos_t) / (n2 * cos_i + n1 * cos_t)
    t_p = 2.0 * n1 * cos_i / (n2 * cos_i + n1 * cos_t)

    kind = cfg.polarization_kind.lower()
    if kind == "p":
        r = r_p
        t = t_p
    else:
        r = r_s
        t = t_s

    admittance_ratio = (n2 * cos_t) / (n1 * cos_i)
    return {
        "r_s": complex(r_s),
        "t_s": complex(t_s),
        "r_p": complex(r_p),
        "t_p": complex(t_p),
        "r": complex(r),
        "t": complex(t),
        "R": float(abs(r) ** 2),
        "T": float(np.real(admittance_ratio) * abs(t) ** 2),
        "R_plus_T": float(abs(r) ** 2 + np.real(admittance_ratio) * abs(t) ** 2),
        "cos_theta_i": float(cos_i),
        "cos_theta_t_real": float(np.real(cos_t)),
        "cos_theta_t_imag": float(np.imag(cos_t)),
    }


def _fresnel_components(cfg: SimulationConfig3D):
    """Build incident/reflected/transmitted k vectors and E amplitudes."""
    n1 = complex(cfg.n_air)
    n2 = complex(cfg.substrate_index)
    kx = cfg.kx
    ky = cfg.ky
    q_air = _positive_sqrt((cfg.k0 * n1) ** 2 - kx**2 - ky**2)
    q_sub = _positive_sqrt((cfg.k0 * n2) ** 2 - kx**2 - ky**2)
    k_inc = np.asarray((kx, ky, -q_air), dtype=np.complex128)
    k_ref = np.asarray((kx, ky, q_air), dtype=np.complex128)
    k_trn = np.asarray((kx, ky, -q_sub), dtype=np.complex128)

    s = cfg.s_polarization_vector
    if cfg.polarization_kind.lower() == "p":
        pol_inc = _p_vector(k_inc, s, n1, cfg)
        pol_ref = _p_vector(k_ref, s, n1, cfg)
        pol_trn = _p_vector(k_trn, s, n2, cfg)
    else:
        pol_inc = s
        pol_ref = s
        pol_trn = s

    ref = fresnel_reference(cfg)
    amp = complex(cfg.incident_amplitude)
    return k_inc, k_ref, k_trn, amp * pol_inc, amp * complex(ref["r"]) * pol_ref, amp * complex(ref["t"]) * pol_trn


def uses_layered_fresnel_background(cfg: SimulationConfig3D) -> bool:
    """Return true when analytic fields mean the flat air/substrate background."""
    return cfg.geometry_kind in {"fresnel_interface", "rectangular_block_grating"}


def electric_field_code_values(cfg: SimulationConfig3D, coords: np.ndarray) -> np.ndarray:
    """Evaluate the normalized analytic E field used by BCs and validation."""
    coords = np.asarray(coords, dtype=np.float64)
    if uses_layered_fresnel_background(cfg):
        k_inc, k_ref, k_trn, e_inc, e_ref, e_trn = _fresnel_components(cfg)
        zeta = pml_complex_z(cfg, coords[:, 2])
        top = coords[:, 2] >= cfg.interface_z
        values = np.zeros((len(coords), 3), dtype=np.complex128)
        if np.any(top):
            phase_inc = _phase(k_inc[0], k_inc[1], k_inc[2], coords[top], zeta[top])
            phase_ref = _phase(k_ref[0], k_ref[1], k_ref[2], coords[top], zeta[top])
            values[top] = phase_inc[:, None] * e_inc[None, :] + phase_ref[:, None] * e_ref[None, :]
        if np.any(~top):
            phase_trn = _phase(k_trn[0], k_trn[1], k_trn[2], coords[~top], zeta[~top])
            values[~top] = phase_trn[:, None] * e_trn[None, :]
        return values

    k = cfg.wavevector
    p = cfg.polarization_vector
    zeta = pml_complex_z(cfg, coords[:, 2])
    phase = _phase(k[0], k[1], k[2], coords, zeta)
    return cfg.incident_amplitude * phase[:, None] * p[None, :]


def magnetic_field_code_values(cfg: SimulationConfig3D, coords: np.ndarray) -> np.ndarray:
    """Evaluate normalized H = (k x E)/(k0 mu_r) in code units."""
    coords = np.asarray(coords, dtype=np.float64)
    if uses_layered_fresnel_background(cfg):
        k_inc, k_ref, k_trn, e_inc, e_ref, e_trn = _fresnel_components(cfg)
        zeta = pml_complex_z(cfg, coords[:, 2])
        top = coords[:, 2] >= cfg.interface_z
        values = np.zeros((len(coords), 3), dtype=np.complex128)
        h_inc = np.cross(k_inc, e_inc) / (cfg.k0 * cfg.mu_r)
        h_ref = np.cross(k_ref, e_ref) / (cfg.k0 * cfg.mu_r)
        h_trn = np.cross(k_trn, e_trn) / (cfg.k0 * cfg.mu_r)
        if np.any(top):
            phase_inc = _phase(k_inc[0], k_inc[1], k_inc[2], coords[top], zeta[top])
            phase_ref = _phase(k_ref[0], k_ref[1], k_ref[2], coords[top], zeta[top])
            values[top] = phase_inc[:, None] * h_inc[None, :] + phase_ref[:, None] * h_ref[None, :]
        if np.any(~top):
            phase_trn = _phase(k_trn[0], k_trn[1], k_trn[2], coords[~top], zeta[~top])
            values[~top] = phase_trn[:, None] * h_trn[None, :]
        return values

    k = cfg.wavevector
    p = cfg.polarization_vector
    zeta = pml_complex_z(cfg, coords[:, 2])
    phase = _phase(k[0], k[1], k[2], coords, zeta)
    h_code = np.cross(k, p) / (cfg.k0 * cfg.mu_r)
    return cfg.incident_amplitude * phase[:, None] * h_code[None, :]
