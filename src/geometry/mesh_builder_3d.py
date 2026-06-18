from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from mpi4py import MPI

from dolfinx import io, mesh

from ..common.config_3d import SimulationConfig3D


@dataclass
class AirBox3DMesh:
    mesh: mesh.Mesh
    cell_tags: mesh.MeshTags
    facet_tags: mesh.MeshTags
    boundary_facets: np.ndarray


def _mark_boundary_facets(msh: mesh.Mesh, cfg: SimulationConfig3D) -> tuple[mesh.MeshTags, np.ndarray]:
    """Tag the six exterior box faces used by Dirichlet and Floquet logic."""
    fdim = msh.topology.dim - 1
    markers = (
        (cfg.tags.x_min, lambda x: np.isclose(x[0], cfg.x_min)),
        (cfg.tags.x_max, lambda x: np.isclose(x[0], cfg.x_max)),
        (cfg.tags.y_min, lambda x: np.isclose(x[1], cfg.y_min)),
        (cfg.tags.y_max, lambda x: np.isclose(x[1], cfg.y_max)),
        (cfg.tags.z_min, lambda x: np.isclose(x[2], cfg.domain_z_min)),
        (cfg.tags.z_max, lambda x: np.isclose(x[2], cfg.domain_z_max)),
    )
    facet_indices: list[np.ndarray] = []
    facet_values: list[np.ndarray] = []
    for tag, marker in markers:
        facets = mesh.locate_entities_boundary(msh, fdim, marker)
        facet_indices.append(facets)
        facet_values.append(np.full(len(facets), tag, dtype=np.int32))

    if facet_indices:
        indices = np.concatenate(facet_indices).astype(np.int32)
        values = np.concatenate(facet_values).astype(np.int32)
        order = np.argsort(indices)
        indices = indices[order]
        values = values[order]
    else:
        indices = np.asarray([], dtype=np.int32)
        values = np.asarray([], dtype=np.int32)

    return mesh.meshtags(msh, fdim, indices, values), np.unique(indices)


def _mark_cells(msh: mesh.Mesh, cfg: SimulationConfig3D) -> mesh.MeshTags:
    """Tag air, substrate, top PML, and bottom PML cells by cell midpoint."""
    tdim = msh.topology.dim
    index_map = msh.topology.index_map(tdim)
    num_cells = index_map.size_local + index_map.num_ghosts
    cells = np.arange(num_cells, dtype=np.int32)
    midpoints = mesh.compute_midpoints(msh, tdim, cells)

    values = np.full(num_cells, cfg.tags.air, dtype=np.int32)
    z = midpoints[:, 2]
    tol = 1.0e-10 * max(abs(cfg.domain_z_max - cfg.domain_z_min), 1.0)

    if cfg.use_pml and cfg.pml_bottom_thickness > 0.0:
        values[z < cfg.physical_z_min - tol] = cfg.tags.bottom_pml
    if cfg.use_pml and cfg.pml_top_thickness > 0.0:
        values[z > cfg.physical_z_max + tol] = cfg.tags.top_pml
    if cfg.geometry_kind == "fresnel_interface":
        physical = (z >= cfg.physical_z_min - tol) & (z <= cfg.physical_z_max + tol)
        values[physical & (z < cfg.interface_z)] = cfg.tags.substrate

    return mesh.meshtags(msh, tdim, cells, values)


def build_airbox_mesh_3d(cfg: SimulationConfig3D, out_dir: Path) -> AirBox3DMesh:
    """Build a structured tetrahedral 3D box mesh for staged verification.

    The mesh is intentionally simple in Stage 2: all complexity is in the
    material tags and boundary conditions, which makes failures easier to
    localize before grating geometry is introduced in Stage 3.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = MPI.COMM_WORLD
    points = [
        np.asarray((cfg.x_min, cfg.y_min, cfg.domain_z_min), dtype=np.float64),
        np.asarray((cfg.x_max, cfg.y_max, cfg.domain_z_max), dtype=np.float64),
    ]
    msh = mesh.create_box(
        comm,
        points,
        cfg.mesh_cells,
        cell_type=mesh.CellType.tetrahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    msh.name = cfg.case_name
    msh.topology.create_connectivity(msh.topology.dim - 1, msh.topology.dim)
    cell_tags = _mark_cells(msh, cfg)
    facet_tags, boundary_facets = _mark_boundary_facets(msh, cfg)

    try:
        with io.XDMFFile(comm, out_dir / "mesh_3d.xdmf", "w") as xdmf:
            xdmf.write_mesh(msh)
    except Exception as exc:  # pragma: no cover - best-effort artifact
        if comm.rank == 0:
            (out_dir / "mesh_3d_xdmf_warning.txt").write_text(str(exc), encoding="utf-8")

    return AirBox3DMesh(mesh=msh, cell_tags=cell_tags, facet_tags=facet_tags, boundary_facets=boundary_facets)
