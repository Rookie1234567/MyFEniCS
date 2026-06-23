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
    mesh_cell_type_resolved: str
    mesh_cells_resolved: tuple[int, int, int]
    z_alignment_warnings: list[str]


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
    """Tag air, substrate, grating, top PML, and bottom PML cells by midpoint."""
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
    if cfg.geometry_kind in {"fresnel_interface", "rectangular_block_grating"}:
        physical = (z >= cfg.physical_z_min - tol) & (z <= cfg.physical_z_max + tol)
        values[physical & (z < cfg.interface_z)] = cfg.tags.substrate
    if cfg.geometry_kind == "rectangular_block_grating" and cfg.has_grating_block:
        x = midpoints[:, 0]
        y = midpoints[:, 1]
        physical = (z >= cfg.physical_z_min - tol) & (z <= cfg.physical_z_max + tol)
        in_block = (
            physical
            & (x >= cfg.grating_x_min - tol)
            & (x <= cfg.grating_x_max + tol)
            & (y >= cfg.grating_y_min - tol)
            & (y <= cfg.grating_y_max + tol)
            & (z >= cfg.grating_z_min - tol)
            & (z <= cfg.grating_z_max + tol)
        )
        values[in_block] = cfg.tags.grating

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


def _required_z_planes(cfg: SimulationConfig3D) -> list[tuple[str, float]]:
    planes: list[tuple[str, float]] = []
    if cfg.use_pml:
        planes.append(("physical_z_min", cfg.physical_z_min))
        planes.append(("physical_z_max", cfg.physical_z_max))
    if cfg.geometry_kind in {"fresnel_interface", "rectangular_block_grating"}:
        planes.append(("interface_z", cfg.interface_z))
    if cfg.geometry_kind == "rectangular_block_grating" and cfg.has_grating_block:
        planes.append(("grating_z_max", cfg.grating_z_max))
    return planes


def _hexa_mesh_cells(cfg: SimulationConfig3D, comm_size: int) -> tuple[int, int, int]:
    """Keep periodic hexa smoke meshes from creating empty MPI ranks."""
    cells = [int(value) for value in cfg.mesh_cells]
    if cfg.use_floquet_xy:
        cells[0] = max(cells[0], 2)
        cells[1] = max(cells[1], 2)
        cells[2] = max(cells[2], 2)
    axis = 2
    while cells[0] * cells[1] * cells[2] < comm_size:
        cells[axis] += 1
        axis = (axis + 2) % 3
    return tuple(cells)


def _z_alignment_warnings(cfg: SimulationConfig3D, mesh_cells_resolved: tuple[int, int, int]) -> list[str]:
    """Report when uniform hexahedral z planes do not contain material breaks."""
    if cfg.mesh_cell_type_resolved != "hexahedron":
        return []
    required = _required_z_planes(cfg)
    if not required:
        return []
    z_grid = np.linspace(cfg.domain_z_min, cfg.domain_z_max, mesh_cells_resolved[2] + 1)
    tol = 1.0e-10 * max(abs(cfg.domain_z_max - cfg.domain_z_min), 1.0)
    warnings: list[str] = []
    for name, value in required:
        if not np.any(np.isclose(z_grid, value, atol=tol, rtol=0.0)):
            warnings.append(
                f"{name}={value:g} nm is not on a hexahedral z grid plane for "
                f"mesh_target_size={cfg.mesh_target_size:g} nm; cell tags use midpoint classification."
            )
    return warnings


def _grid_contains(grid: np.ndarray, value: float, tol: float) -> bool:
    return bool(np.any(np.isclose(grid, value, atol=tol, rtol=0.0)))


def _validate_stage4_hexa_alignment(cfg: SimulationConfig3D, mesh_cells_resolved: tuple[int, int, int]) -> None:
    """Require every Stage-4 material break to lie on a hexahedral grid plane."""
    if cfg.geometry_kind != "rectangular_block_grating":
        return
    if cfg.mesh_cell_type_resolved != "hexahedron":
        raise ValueError("stage4_block_grating requires a hexahedron mesh for explicit edge Floquet constraints.")
    if cfg.nedelec_degree != 1:
        raise NotImplementedError("stage4_block_grating currently supports only degree=1 N1curl.")
    if cfg.scattering_background.lower() != "layered":
        raise ValueError("stage4_block_grating currently requires scattering_background='layered'.")
    if cfg.grating_width_x < 0.0 or cfg.grating_width_y < 0.0 or cfg.grating_height < 0.0:
        raise ValueError("Stage-4 grating dimensions must be non-negative.")
    if cfg.has_grating_block:
        if not (cfg.x_min <= cfg.grating_x_min < cfg.grating_x_max <= cfg.x_max):
            raise ValueError("Stage-4 grating x bounds must lie inside one periodic cell.")
        if not (cfg.y_min <= cfg.grating_y_min < cfg.grating_y_max <= cfg.y_max):
            raise ValueError("Stage-4 grating y bounds must lie inside one periodic cell.")
        if not (cfg.physical_z_min <= cfg.grating_z_min < cfg.grating_z_max <= cfg.physical_z_max):
            raise ValueError("Stage-4 grating z bounds must lie inside the physical z domain.")

    axes = {
        "x": (
            np.linspace(cfg.x_min, cfg.x_max, mesh_cells_resolved[0] + 1),
            [("grating_x_min", cfg.grating_x_min), ("grating_x_max", cfg.grating_x_max)] if cfg.has_grating_block else [],
        ),
        "y": (
            np.linspace(cfg.y_min, cfg.y_max, mesh_cells_resolved[1] + 1),
            [("grating_y_min", cfg.grating_y_min), ("grating_y_max", cfg.grating_y_max)] if cfg.has_grating_block else [],
        ),
        "z": (
            np.linspace(cfg.domain_z_min, cfg.domain_z_max, mesh_cells_resolved[2] + 1),
            _required_z_planes(cfg),
        ),
    }
    messages: list[str] = []
    for axis_name, (grid, required) in axes.items():
        tol = 1.0e-10 * max(abs(float(grid[-1] - grid[0])), 1.0)
        for name, value in required:
            if not _grid_contains(grid, value, tol):
                messages.append(
                    f"{name}={value:g} nm is not on the uniform {axis_name}-grid; "
                    f"resolved {axis_name}-cell count is {len(grid) - 1}."
                )
    if messages:
        hint = (
            "Stage-4 hexa meshes do not use midpoint approximation for material boundaries. "
            "Choose mesh_target_size or period/block dimensions so every interface is a grid plane."
        )
        raise ValueError(hint + " " + " ".join(messages))


def build_airbox_mesh_3d(cfg: SimulationConfig3D, out_dir: Path) -> AirBox3DMesh:
    """Build a structured tetrahedral 3D box mesh for staged verification.

    The mesh is intentionally simple in Stage 2: all complexity is in the
    material tags and boundary conditions, which makes failures easier to
    localize before grating geometry is introduced in Stage 3.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = MPI.COMM_WORLD
    mesh_cell_type_resolved = cfg.mesh_cell_type_resolved
    mesh_cells_resolved = _hexa_mesh_cells(cfg, comm.size) if mesh_cell_type_resolved == "hexahedron" else cfg.mesh_cells
    _validate_stage4_hexa_alignment(cfg, mesh_cells_resolved)
    z_alignment_warnings = _z_alignment_warnings(cfg, mesh_cells_resolved)

    if mesh_cell_type_resolved == "hexahedron":
        points = [
            np.asarray((cfg.x_min, cfg.y_min, cfg.domain_z_min), dtype=np.float64),
            np.asarray((cfg.x_max, cfg.y_max, cfg.domain_z_max), dtype=np.float64),
        ]
        msh = mesh.create_box(
            comm,
            points,
            mesh_cells_resolved,
            cell_type=mesh.CellType.hexahedron,
            ghost_mode=mesh.GhostMode.shared_facet,
        )
        if comm.rank == 0:
            note_lines = [
                "Using dolfinx.mesh.create_box with hexahedron cells.",
                "This is the default low-memory 3D Floquet mesh because opposite periodic faces are structured.",
            ]
            if cfg.geometry_kind == "rectangular_block_grating":
                note_lines.append(
                    "Stage-4 rectangular block tags are aligned to hexahedral grid planes; no midpoint fallback is used."
                )
            note_lines.extend(f"WARNING: {message}" for message in z_alignment_warnings)
            (out_dir / "mesh_3d_partition_note.txt").write_text("\n".join(note_lines) + "\n", encoding="utf-8")
    elif comm.size > 1:
        points = [
            np.asarray((cfg.x_min, cfg.y_min, cfg.domain_z_min), dtype=np.float64),
            np.asarray((cfg.x_max, cfg.y_max, cfg.domain_z_max), dtype=np.float64),
        ]
        msh = mesh.create_box(
            comm,
            points,
            mesh_cells_resolved,
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

    return AirBox3DMesh(
        mesh=msh,
        cell_tags=cell_tags,
        facet_tags=facet_tags,
        boundary_facets=boundary_facets,
        mesh_cell_type_resolved=mesh_cell_type_resolved,
        mesh_cells_resolved=mesh_cells_resolved,
        z_alignment_warnings=z_alignment_warnings,
    )
