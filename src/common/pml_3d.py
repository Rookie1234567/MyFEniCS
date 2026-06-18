from __future__ import annotations

import ufl

from .config_3d import SimulationConfig3D


def _z_stretch_derivative(z, cfg: SimulationConfig3D, side: str):
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
    """Return full-vector Maxwell tensors for a z-only complex stretch."""
    s_z = _z_stretch_derivative(x[2], cfg, side)
    jacobian = ufl.as_matrix(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, s_z)))
    inv_jacobian = ufl.inv(jacobian)
    eps_pml = ufl.det(jacobian) * inv_jacobian * eps_background * ufl.transpose(inv_jacobian)
    mu_pml = ufl.det(jacobian) * inv_jacobian * 1.0 * ufl.transpose(inv_jacobian)
    return eps_pml, mu_pml
