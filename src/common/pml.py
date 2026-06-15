from __future__ import annotations

import ufl

from .config import SimulationConfig


def curl_3d(field):
    """Return the 3D curl vector for a 2D in-plane electric field."""
    return ufl.as_vector((0, 0, field[1].dx(0) - field[0].dx(1)))


def field_3d(field):
    return ufl.as_vector((field[0], field[1], 0))


def _pml_coordinate(coord, alpha: float, k0: float, l_dom: float, l_pml: float):
    """Official DOLFINx PML complex coordinate continuation."""
    half_dom = 0.5 * l_dom
    half_pml = 0.5 * l_pml
    return coord + 1j * alpha / k0 * coord * (ufl.algebra.Abs(coord) - half_dom) / (half_pml - half_dom) ** 2


def _y_pml_coordinate(y, cfg: SimulationConfig, pml_thickness: float):
    y_center = 0.5 * (cfg.physical_y_min + cfg.physical_y_max)
    eta = y - y_center
    l_dom = cfg.physical_y_max - cfg.physical_y_min
    l_pml = l_dom + 2.0 * pml_thickness
    return y_center + _pml_coordinate(eta, cfg.pml_alpha, cfg.k0, l_dom, l_pml)


def _pml_tensors_from_coordinate_map(pml_coordinates, eps_background: complex):
    J2 = ufl.grad(pml_coordinates)
    J = ufl.as_matrix(((J2[0, 0], 0, 0), (0, J2[1, 1], 0), (0, 0, 1.0)))
    A = ufl.inv(J)
    eps_pml = ufl.det(J) * A * eps_background * ufl.transpose(A)
    mu_pml = ufl.det(J) * A * 1.0 * ufl.transpose(A)
    return eps_pml, mu_pml


def top_pml_tensors(x, cfg: SimulationConfig):
    """Top PML is the complex-coordinate continuation of air."""
    y_pml = _y_pml_coordinate(x[1], cfg, cfg.pml_top_thickness)
    return _pml_tensors_from_coordinate_map(ufl.as_vector((x[0], y_pml)), cfg.eps_air)


def bottom_pml_tensors(x, cfg: SimulationConfig):
    """Bottom PML is the complex-coordinate continuation of the substrate."""
    y_pml = _y_pml_coordinate(x[1], cfg, cfg.pml_bottom_thickness)
    return _pml_tensors_from_coordinate_map(ufl.as_vector((x[0], y_pml)), cfg.eps_substrate)


def _scalar_pml_coefficients_from_coordinate_map(pml_coordinates, eps_background: complex):
    """Return scalar-Helmholtz PML coefficients for TE Ez.

    For the scalar equation grad^2(Ez) + k0^2 eps Ez = 0, a complex coordinate
    map with Jacobian J gives the weak-form tensor det(J) J^{-1} J^{-T} in the
    gradient term and det(J) eps in the mass term.
    """
    J = ufl.grad(pml_coordinates)
    A = ufl.inv(J)
    grad_tensor = ufl.det(J) * A * ufl.transpose(A)
    eps_scaled = ufl.det(J) * eps_background
    return grad_tensor, eps_scaled


def top_scalar_pml_coefficients(x, cfg: SimulationConfig):
    """Top TE scalar PML: complex-coordinate continuation of air."""
    y_pml = _y_pml_coordinate(x[1], cfg, cfg.pml_top_thickness)
    return _scalar_pml_coefficients_from_coordinate_map(
        ufl.as_vector((x[0], y_pml)),
        cfg.eps_air,
    )


def bottom_scalar_pml_coefficients(x, cfg: SimulationConfig):
    """Bottom TE scalar PML: complex-coordinate continuation of substrate."""
    y_pml = _y_pml_coordinate(x[1], cfg, cfg.pml_bottom_thickness)
    return _scalar_pml_coefficients_from_coordinate_map(
        ufl.as_vector((x[0], y_pml)),
        cfg.eps_substrate,
    )
