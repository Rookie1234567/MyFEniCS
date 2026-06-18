from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import ufl
from basix.ufl import element
from mpi4py import MPI

from dolfinx import default_real_type, io, mesh

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


def _axis_coordinates(start: float, stop: float, target_size: float, required: tuple[float, ...] = ()) -> np.ndarray:
    """Return sorted coordinates that include required material/PML planes."""
    length = stop - start
    num_cells = max(1, int(np.ceil(length / target_size)))
    base = np.linspace(start, stop, num_cells + 1)
    values = [float(value) for value in base]
    tol = 1.0e-10 * max(abs(length), 1.0)
    for value in required:
        if start + tol < value < stop - tol:
            values.append(float(value))
    values = sorted(values)
    unique = [values[0]]
    for value in values[1:]:
        if abs(value - unique[-1]) > tol:
            unique.append(value)
    return np.asarray(unique, dtype=np.float64)


def _structured_tet_mesh(msh_comm: MPI.Intracomm, cfg: SimulationConfig3D) -> mesh.Mesh:
    """Create a structured tet mesh with z breaks at Stage-2 material planes.

    ``mesh.create_box`` only creates uniform axis spacing.  For Fresnel and PML
    validation, the interface and PML entrances must be real cell faces even on
    coarse smoke meshes; otherwise midpoint-based tags smear the manufactured
    reference problem.
    """
    required_z = [cfg.physical_z_min, cfg.physical_z_max]
    if cfg.geometry_kind == "fresnel_interface":
        required_z.append(cfg.interface_z)
    x_values = _axis_coordinates(cfg.x_min, cfg.x_max, cfg.mesh_target_size)
    y_values = _axis_coordinates(cfg.y_min, cfg.y_max, cfg.mesh_target_size)
    z_values = _axis_coordinates(cfg.domain_z_min, cfg.domain_z_max, cfg.mesh_target_size, tuple(required_z))

    nx = len(x_values) - 1
    ny = len(y_values) - 1
    nz = len(z_values) - 1
    points = np.asarray(
        [(x, y, z) for z in z_values for y in y_values for x in x_values],
        dtype=default_real_type,
    )

    def node(i: int, j: int, k: int) -> int:
        return k * len(y_values) * len(x_values) + j * len(x_values) + i

    cells: list[list[int]] = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                v000 = node(i, j, k)
                v100 = node(i + 1, j, k)
                v010 = node(i, j + 1, k)
                v110 = node(i + 1, j + 1, k)
                v001 = node(i, j, k + 1)
                v101 = node(i + 1, j, k + 1)
                v011 = node(i, j + 1, k + 1)
                v111 = node(i + 1, j + 1, k + 1)
                cells.extend(
                    [
                        [v000, v100, v110, v111],
                        [v000, v110, v010, v111],
                        [v000, v010, v011, v111],
                        [v000, v011, v001, v111],
                        [v000, v001, v101, v111],
                        [v000, v101, v100, v111],
                    ]
                )
    coordinate_element = element("Lagrange", "tetrahedron", 1, shape=(3,), dtype=default_real_type)
    domain = ufl.Mesh(coordinate_element)
    partitioner = mesh.create_cell_partitioner(mesh.GhostMode.shared_facet)
    return mesh.create_mesh(msh_comm, np.asarray(cells, dtype=np.int64), domain, points, partitioner=partitioner)


def build_airbox_mesh_3d(cfg: SimulationConfig3D, out_dir: Path) -> AirBox3DMesh:
    """Build a structured tetrahedral 3D box mesh for staged verification.

    The mesh is intentionally simple in Stage 2: all complexity is in the
    material tags and boundary conditions, which makes failures easier to
    localize before grating geometry is introduced in Stage 3.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = MPI.COMM_WORLD
    if comm.size > 1:
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
        if comm.rank == 0:
            (out_dir / "mesh_3d_partition_note.txt").write_text(
                "MPI run: using dolfinx.mesh.create_box fallback. "
                "Serial Stage-2 Fresnel/PML validation uses a custom z-aligned mesh; "
                "distributed custom z-aligned mesh is deferred because it currently "
                "segfaults in this Docker/DOLFINx stack.",
                encoding="utf-8",
            )
    else:
        msh = _structured_tet_mesh(comm, cfg)
    msh.name = cfg.case_name
    msh.topology.create_connectivity(msh.topology.dim - 1, msh.topology.dim)
    cell_tags = _mark_cells(msh, cfg)
    facet_tags, boundary_facets = _mark_boundary_facets(msh, cfg)

    if comm.size == 1:
        try:
            with io.XDMFFile(comm, out_dir / "mesh_3d.xdmf", "w") as xdmf:
                xdmf.write_mesh(msh)
        except Exception as exc:  # pragma: no cover - best-effort artifact
            if comm.rank == 0:
                (out_dir / "mesh_3d_xdmf_warning.txt").write_text(str(exc), encoding="utf-8")
    elif comm.rank == 0:
        (out_dir / "mesh_3d_xdmf_warning.txt").write_text(
            "MPI run: mesh_3d.xdmf is skipped for the custom Stage-2 mesh; "
            "open fields_3d_for_paraview_parallel.pvd after postprocess.",
            encoding="utf-8",
        )

    return AirBox3DMesh(mesh=msh, cell_tags=cell_tags, facet_tags=facet_tags, boundary_facets=boundary_facets)
