from __future__ import annotations

import numpy as np

from dolfinx import fem

from .config import SimulationConfig


def relative_permittivity(mesh_data, cfg: SimulationConfig) -> fem.Function:
    """Piecewise DG0 relative permittivity for air, substrate, grating, and air-filled PMLs."""
    V_eps = fem.functionspace(mesh_data.mesh, ("DG", 0))
    eps = fem.Function(V_eps, name="epsilon_r")
    eps.x.array[:] = np.asarray(cfg.eps_air, dtype=eps.x.array.dtype)

    substrate_cells = mesh_data.cell_tags.find(cfg.tags.substrate)
    grating_cells = mesh_data.cell_tags.find(cfg.tags.grating)
    eps.x.array[substrate_cells] = np.asarray(cfg.eps_substrate, dtype=eps.x.array.dtype)
    eps.x.array[grating_cells] = np.asarray(cfg.eps_grating, dtype=eps.x.array.dtype)
    eps.x.scatter_forward()
    return eps


def background_relative_permittivity(mesh_data, cfg: SimulationConfig) -> fem.Function:
    """DG0 background permittivity used by the scattered-field source term."""
    V_eps = fem.functionspace(mesh_data.mesh, ("DG", 0))
    eps_bg = fem.Function(V_eps, name="epsilon_background")
    eps_bg.x.array[:] = np.asarray(cfg.eps_air, dtype=eps_bg.x.array.dtype)

    if cfg.scattering_background == "air":
        pass
    elif cfg.scattering_background == "layered":
        substrate_cells = mesh_data.cell_tags.find(cfg.tags.substrate)
        eps_bg.x.array[substrate_cells] = np.asarray(cfg.eps_substrate, dtype=eps_bg.x.array.dtype)
    else:
        raise ValueError("scattering_background must be 'air' or 'layered'")

    eps_bg.x.scatter_forward()
    return eps_bg
