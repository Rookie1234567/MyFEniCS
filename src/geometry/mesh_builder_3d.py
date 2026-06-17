from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from mpi4py import MPI

from dolfinx import io, mesh

from ..common.config_3d import AirBox3DConfig


@dataclass
class AirBox3DMesh:
    mesh: mesh.Mesh
    facet_tags: mesh.MeshTags
    boundary_facets: np.ndarray


def _mark_boundary_facets(msh: mesh.Mesh, cfg: AirBox3DConfig) -> tuple[mesh.MeshTags, np.ndarray]:
    fdim = msh.topology.dim - 1
    markers = (
        (cfg.tags.x_min, lambda x: np.isclose(x[0], cfg.x_min)),
        (cfg.tags.x_max, lambda x: np.isclose(x[0], cfg.x_max)),
        (cfg.tags.y_min, lambda x: np.isclose(x[1], cfg.y_min)),
        (cfg.tags.y_max, lambda x: np.isclose(x[1], cfg.y_max)),
        (cfg.tags.z_min, lambda x: np.isclose(x[2], cfg.z_min)),
        (cfg.tags.z_max, lambda x: np.isclose(x[2], cfg.z_max)),
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


def build_airbox_mesh_3d(cfg: AirBox3DConfig, out_dir: Path) -> AirBox3DMesh:
    """Build a simple tetrahedral 3D air box mesh for stage-1 verification."""
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = MPI.COMM_WORLD
    points = [
        np.asarray((cfg.x_min, cfg.y_min, cfg.z_min), dtype=np.float64),
        np.asarray((cfg.x_max, cfg.y_max, cfg.z_max), dtype=np.float64),
    ]
    msh = mesh.create_box(comm, points, cfg.mesh_cells, cell_type=mesh.CellType.tetrahedron)
    msh.name = cfg.case_name
    msh.topology.create_connectivity(msh.topology.dim - 1, msh.topology.dim)
    facet_tags, boundary_facets = _mark_boundary_facets(msh, cfg)

    try:
        with io.XDMFFile(comm, out_dir / "mesh_3d.xdmf", "w") as xdmf:
            xdmf.write_mesh(msh)
    except Exception as exc:  # pragma: no cover - best-effort artifact
        if comm.rank == 0:
            (out_dir / "mesh_3d_xdmf_warning.txt").write_text(str(exc), encoding="utf-8")

    return AirBox3DMesh(mesh=msh, facet_tags=facet_tags, boundary_facets=boundary_facets)
