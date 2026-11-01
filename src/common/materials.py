from __future__ import annotations

import numpy as np

from dolfinx import fem

from .config import SimulationConfig


def relative_permittivity(mesh_data, cfg: SimulationConfig) -> fem.Function:
    """Piecewise DG0 relative permittivity for air, substrate, grating, and air-filled PMLs."""
    V_eps = fem.functionspace(mesh_data.mesh, ("DG", 0))
    eps = fem.Function(V_eps, name="epsilon_r")
    physical_regions = getattr(cfg, "physical_material_regions", None)
    if physical_regions is not None:
        from .gate_cd_materials import validate_gate_cd_region_entries

        entries = validate_gate_cd_region_entries(physical_regions)
        eps.x.array[:] = np.asarray(complex(np.nan, np.nan), dtype=eps.x.array.dtype)
        assigned = np.zeros(len(eps.x.array), dtype=bool)
        num_cells = (
            mesh_data.mesh.topology.index_map(mesh_data.mesh.topology.dim).size_local
            + mesh_data.mesh.topology.index_map(
                mesh_data.mesh.topology.dim
            ).num_ghosts
        )
        for entry in entries:
            cells = np.asarray(
                mesh_data.cell_tags.find(int(entry["tag"])), dtype=np.int64
            )
            if cells.size == 0:
                raise ValueError(
                    f"gate_cd physical region {entry['label']} has no tagged cells"
                )
            if np.any(cells < 0) or np.any(cells >= num_cells):
                raise ValueError("gate_cd cell tag index exceeds the local mesh")
            dof_groups = [
                np.asarray(V_eps.dofmap.cell_dofs(int(cell)), dtype=np.int64)
                for cell in cells
            ]
            dofs = (
                np.concatenate(dof_groups)
                if dof_groups
                else np.empty(0, dtype=np.int64)
            )
            if np.any(dofs < 0) or np.any(dofs >= len(eps.x.array)):
                raise ValueError("gate_cd DG0 cell map exceeds coefficient storage")
            if np.any(assigned[dofs]):
                raise ValueError("gate_cd physical material tags overlap in DG0 storage")
            eps.x.array[dofs] = np.asarray(
                complex(entry["epsilon_r"]), dtype=eps.x.array.dtype
            )
            assigned[dofs] = True
        if not np.all(assigned):
            raise ValueError(
                "gate_cd physical material map does not cover every local DG0 cell"
            )
        eps.x.scatter_forward()
        return eps
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
