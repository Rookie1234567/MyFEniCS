from __future__ import annotations

import ufl

from .config_3d import SimulationConfig3D


def z_stretch_derivative_value(z: float, cfg: SimulationConfig3D, side: str) -> complex:
    """Return dz_tilde/dz for the z-only cubic PML stretch.

    Both top and bottom use an outward-depth convention.  With the project
    phase convention exp(i k·r) exp(-i omega t), this makes outgoing waves
    decay in their corresponding PML layer.
    """
    if side == "top":
        thickness = cfg.pml_top_thickness
        distance = (z - cfg.physical_z_max) / thickness
    elif side == "bottom":
        thickness = cfg.pml_bottom_thickness
        distance = (cfg.physical_z_min - z) / thickness
    else:
        raise ValueError("side must be 'top' or 'bottom'.")
    if thickness <= 0.0:
        raise ValueError("PML thickness must be positive when evaluating the stretch.")
    return 1.0 + 1j * cfg.pml_alpha / cfg.k0 * 3.0 * distance**2 / thickness


def z_pml_diagonal_values(z: float, cfg: SimulationConfig3D, side: str, eps_background: complex):
    """Return diagonal eps and mu^{-1} factors for direct unit tests."""
    s_z = z_stretch_derivative_value(z, cfg, side)
    eps_diag = (
        complex(eps_background) * s_z,
        complex(eps_background) * s_z,
        complex(eps_background) / s_z,
    )
    mu_inv_diag = (1.0 / s_z, 1.0 / s_z, s_z)
    return eps_diag, mu_inv_diag


def _z_stretch_derivative(z, cfg: SimulationConfig3D, side: str):
    """UFL version of ``z_stretch_derivative_value`` for variational forms."""
    if side == "top":
        thickness = cfg.pml_top_thickness
        distance = (z - cfg.physical_z_max) / thickness
    elif side == "bottom":
        thickness = cfg.pml_bottom_thickness
        distance = (cfg.physical_z_min - z) / thickness
    else:
        raise ValueError("side must be 'top' or 'bottom'.")
    return 1.0 + 1j * cfg.pml_alpha / cfg.k0 * 3.0 * distance**2 / thickness


def z_pml_tensors(x, cfg: SimulationConfig3D, side: str, eps_background: complex):
    """Return full-vector Maxwell tensors for a z-only complex stretch.

    The returned second tensor is mu, not mu^{-1}; the solver explicitly takes
    its inverse in the curl-curl term.  The test helper above exposes the final
    mu^{-1} diagonal used mathematically.
    """
    s_z = _z_stretch_derivative(x[2], cfg, side)
    jacobian = ufl.as_matrix(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, s_z)))
    inv_jacobian = ufl.inv(jacobian)
    eps_pml = ufl.det(jacobian) * inv_jacobian * eps_background * ufl.transpose(inv_jacobian)
    mu_pml = ufl.det(jacobian) * inv_jacobian * 1.0 * ufl.transpose(inv_jacobian)
    return eps_pml, mu_pml
