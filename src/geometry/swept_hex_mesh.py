"""Small first-order mesh builder for separable z-swept hexahedra.

This is deliberately narrower than the general gate_cd mesh planner.  It
supports a conforming tensor topology whose x/y node locations may vary with z
while every cross-section remains axis aligned.  It is intended for bounded
mapped-cell verification and explicit opt-in mapped workflows.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import ufl
from basix.ufl import element
from dolfinx import default_real_type, mesh
from mpi4py import MPI


def _cell_geometry_key(coordinates: np.ndarray) -> bytes:
    values = np.asarray(coordinates, dtype=np.float64)
    if values.shape != (8, 3) or not np.all(np.isfinite(values)):
        raise ValueError("cell geometry keys require eight finite three-vectors")
    order = np.lexsort((values[:, 2], values[:, 1], values[:, 0]))
    return np.ascontiguousarray(values[order], dtype=np.float64).tobytes()


def _remap_input_cell_tags(
    input_cells: np.ndarray,
    input_points: np.ndarray,
    input_tags: np.ndarray,
    mesh_cell_coordinates: Sequence[np.ndarray],
) -> np.ndarray:
    """Map input-order tags to post-create_mesh cells by exact vertex identity."""

    cells = np.asarray(input_cells, dtype=np.int64)
    points = np.asarray(input_points, dtype=np.float64)
    tags = np.asarray(input_tags, dtype=np.int32)
    if tags.shape != (len(cells),):
        raise ValueError("input tags must have one entry per input cell")
    key_to_tag: dict[bytes, int] = {}
    for input_index, cell in enumerate(cells):
        key = _cell_geometry_key(points[cell])
        if key in key_to_tag:
            raise ValueError("input mesh contains duplicate cell geometry keys")
        key_to_tag[key] = int(tags[input_index])
    result = np.empty(len(mesh_cell_coordinates), dtype=np.int32)
    seen: set[bytes] = set()
    for mesh_index, coordinates in enumerate(mesh_cell_coordinates):
        key = _cell_geometry_key(coordinates)
        if key not in key_to_tag:
            raise RuntimeError("created mesh cell does not match an input cell")
        if key in seen:
            raise RuntimeError("created mesh contains duplicate cell geometry keys")
        seen.add(key)
        result[mesh_index] = key_to_tag[key]
    if len(seen) != len(key_to_tag):
        raise RuntimeError("create_mesh omitted one or more tagged input cells")
    return result


def build_swept_hex_mesh(
    comm: MPI.Intracomm,
    z_values: Sequence[float],
    x_nodes_by_z: Sequence[Sequence[float]],
    y_nodes_by_z: Sequence[Sequence[float]],
    *,
    cell_tags: Sequence[int] | None = None,
    require_periodic_xy: bool = False,
):
    """Create a conforming Q1 hex mesh from explicit z-section node arrays.

    ``x_nodes_by_z[k]`` and ``y_nodes_by_z[k]`` give the full ordered x/y
    node coordinates on section ``z_values[k]``.  Their lengths must remain
    fixed across sections.  Each cell is connected in DOLFINx hexahedron local
    vertex order; no coordinate sorting or midpoint reconstruction is used.

    When ``require_periodic_xy`` is true, each opposing periodic boundary must
    be a pure translation for every z section.  This establishes matching
    periodic coordinates, not an MPC phase relation.
    """

    z = np.asarray(z_values, dtype=np.float64)
    x_sections = np.asarray(x_nodes_by_z, dtype=np.float64)
    y_sections = np.asarray(y_nodes_by_z, dtype=np.float64)
    if comm.size != 1:
        raise NotImplementedError(
            "the bounded swept-hex builder currently requires MPI.COMM_SELF"
        )
    if z.ndim != 1 or len(z) < 2 or not np.all(np.isfinite(z)):
        raise ValueError("z_values must be a finite 1-D sequence with >=2 entries")
    if np.any(np.diff(z) <= 0.0):
        raise ValueError("z_values must be strictly increasing")
    if x_sections.ndim != 2 or x_sections.shape[0] != len(z):
        raise ValueError("x_nodes_by_z must have shape (len(z_values), nx+1)")
    if y_sections.ndim != 2 or y_sections.shape[0] != len(z):
        raise ValueError("y_nodes_by_z must have shape (len(z_values), ny+1)")
    if x_sections.shape[1] < 2 or y_sections.shape[1] < 2:
        raise ValueError("each section must contain at least two x/y nodes")
    for name, sections in (("x", x_sections), ("y", y_sections)):
        if not np.all(np.isfinite(sections)):
            raise ValueError(f"{name} sections contain non-finite coordinates")
        if np.any(np.diff(sections, axis=1) <= 0.0):
            raise ValueError(f"{name} section coordinates must strictly increase")
    if require_periodic_xy:
        if not np.array_equal(x_sections[:, 0], x_sections[0, 0] * np.ones(len(z))):
            raise ValueError("periodic x-min boundary moves with z")
        if not np.array_equal(x_sections[:, -1], x_sections[0, -1] * np.ones(len(z))):
            raise ValueError("periodic x-max boundary moves with z")
        if not np.array_equal(y_sections[:, 0], y_sections[0, 0] * np.ones(len(z))):
            raise ValueError("periodic y-min boundary moves with z")
        if not np.array_equal(y_sections[:, -1], y_sections[0, -1] * np.ones(len(z))):
            raise ValueError("periodic y-max boundary moves with z")

    nz = len(z) - 1
    ny = y_sections.shape[1] - 1
    nx = x_sections.shape[1] - 1
    points = np.empty((len(z) * (ny + 1) * (nx + 1), 3), dtype=np.float64)

    def node(i: int, j: int, k: int) -> int:
        return k * (ny + 1) * (nx + 1) + j * (nx + 1) + i

    for k, zk in enumerate(z):
        for j, yv in enumerate(y_sections[k]):
            for i, xv in enumerate(x_sections[k]):
                points[node(i, j, k)] = (xv, yv, zk)
    cells = np.empty((nz * ny * nx, 8), dtype=np.int64)
    cell = 0
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                cells[cell] = (
                    node(i, j, k),
                    node(i + 1, j, k),
                    node(i, j + 1, k),
                    node(i + 1, j + 1, k),
                    node(i, j, k + 1),
                    node(i + 1, j, k + 1),
                    node(i, j + 1, k + 1),
                    node(i + 1, j + 1, k + 1),
                )
                cell += 1
    if cell_tags is not None:
        tags = np.asarray(cell_tags, dtype=np.int32)
        if tags.shape != (len(cells),):
            raise ValueError("cell_tags must contain one value per input cell")
    else:
        tags = None

    coordinate_element = element(
        "Lagrange",
        "hexahedron",
        1,
        shape=(3,),
        dtype=default_real_type,
    )
    domain = ufl.Mesh(coordinate_element)
    partitioner = mesh.create_cell_partitioner(mesh.GhostMode.shared_facet)
    mesh_points = np.asarray(points, dtype=default_real_type)
    msh = mesh.create_mesh(
        comm,
        cells,
        domain,
        mesh_points,
        partitioner=partitioner,
    )
    if tags is None:
        return msh, None
    owned_cells = int(msh.topology.index_map(msh.topology.dim).size_local)
    if owned_cells != len(tags):
        raise RuntimeError("MPI.COMM_SELF mesh unexpectedly changed cell ownership")
    local_coordinates = [
        msh.geometry.x[np.asarray(msh.geometry.dofmap[cell], dtype=np.int64)]
        for cell in range(owned_cells)
    ]
    mesh_order_tags = _remap_input_cell_tags(
        cells, mesh_points, tags, local_coordinates
    )
    meshtags = mesh.meshtags(
        msh,
        msh.topology.dim,
        np.arange(owned_cells, dtype=np.int32),
        mesh_order_tags,
    )
    return msh, meshtags
