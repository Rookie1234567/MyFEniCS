"""Independent runtime mesh/function-space identity for Task002 Full3D p5."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

from .provenance import canonical_hash
from .task002_full3d import build_task002_full3d_config, task002_full3d_topology_identity
from .task002_schema import Task002ForwardParameters


RUNTIME_SCHEMA = "task002.actual-runtime-topology.v1"


def _point(value: np.ndarray) -> tuple[float, float, float]:
    return tuple(float(x) for x in np.round(np.asarray(value)[:3], 12))


def _entity_key(coordinates: np.ndarray) -> tuple[tuple[float, float, float], ...]:
    return tuple(sorted(_point(row) for row in coordinates))


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _expected_n1curl_dofs(nx: int, ny: int, nz: int, degree: int) -> int:
    edges = (nx * (ny + 1) * (nz + 1) + (nx + 1) * ny * (nz + 1)
             + (nx + 1) * (ny + 1) * nz)
    faces = (nx * ny * (nz + 1) + nx * (ny + 1) * nz
             + (nx + 1) * ny * nz)
    cells = nx * ny * nz
    return int(edges * degree + faces * 2 * degree * (degree - 1)
               + cells * 3 * degree * (degree - 1) ** 2)


def _planned_cells(axes: tuple[np.ndarray, np.ndarray, np.ndarray]) -> list[tuple]:
    x, y, z = axes
    return sorted(
        _entity_key(np.asarray([
            (x[i], y[j], z[k]), (x[i + 1], y[j], z[k]),
            (x[i], y[j + 1], z[k]), (x[i + 1], y[j + 1], z[k]),
            (x[i], y[j], z[k + 1]), (x[i + 1], y[j], z[k + 1]),
            (x[i], y[j + 1], z[k + 1]), (x[i + 1], y[j + 1], z[k + 1]),
        ]))
        for k in range(len(z) - 1) for j in range(len(y) - 1)
        for i in range(len(x) - 1)
    )


def _planned_boundary(axes, cfg) -> list[tuple]:
    x, y, z = axes
    rows = []
    for tag, axis, side in (
        (cfg.tags.x_min, 0, 0), (cfg.tags.x_max, 0, -1),
        (cfg.tags.y_min, 1, 0), (cfg.tags.y_max, 1, -1),
        (cfg.tags.z_min, 2, 0), (cfg.tags.z_max, 2, -1),
    ):
        fixed = axes[axis][side]
        other = [value for i, value in enumerate(axes) if i != axis]
        for i in range(len(other[0]) - 1):
            for j in range(len(other[1]) - 1):
                points = []
                for a, b in ((i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)):
                    coordinate = [0.0, 0.0, 0.0]
                    coordinate[axis] = fixed
                    remaining = [dim for dim in range(3) if dim != axis]
                    coordinate[remaining[0]] = other[0][a]
                    coordinate[remaining[1]] = other[1][b]
                    points.append(coordinate)
                rows.append((int(tag), _entity_key(np.asarray(points))))
    return sorted(rows)


def planned_runtime_identity(parameters: Task002ForwardParameters) -> dict[str, Any]:
    """Build independently comparable identities from the frozen plan."""

    cfg = build_task002_full3d_config(parameters)
    planned = task002_full3d_topology_identity(parameters)
    axes = tuple(np.round(np.asarray(planned["resolved_axes_nm"][name], dtype=float), 12)
                 for name in ("x", "y", "z"))
    cells = _planned_cells(axes)
    tags = []
    for cell in cells:
        points = np.asarray(cell)
        midpoint = np.mean(points, axis=0)
        x, z = midpoint[0], midpoint[2]
        if z < cfg.interface_z:
            tag = cfg.tags.substrate
        elif cfg.grating_x_min < x < cfg.grating_x_max and z < cfg.grating_z_max:
            tag = cfg.tags.grating
        else:
            tag = cfg.tags.air
        tags.append((cell, int(tag)))
    boundary = _planned_boundary(axes, cfg)
    counts = tuple(len(axis) - 1 for axis in axes)
    degree = int(cfg.nedelec_degree)
    return {
        "axis_values_nm": {name: axis.tolist() for name, axis in zip(("x", "y", "z"), axes)},
        "axis_cell_counts": list(counts), "global_cell_count": len(cells),
        "canonical_cell_geometry_sha256": _sha(cells),
        "material_cell_geometry_tag_sha256": _sha(tags),
        "boundary_facet_geometry_tag_sha256": _sha(boundary),
        "periodic_boundary_facet_counts": {
            str(cfg.tags.x_min): counts[1] * counts[2],
            str(cfg.tags.x_max): counts[1] * counts[2],
            str(cfg.tags.y_min): counts[0] * counts[2],
            str(cfg.tags.y_max): counts[0] * counts[2],
        },
        "element": {"family": "N1curl", "cell": "hexahedron", "degree": degree},
        "expected_global_dof_count": _expected_n1curl_dofs(*counts, degree),
    }


def actual_runtime_mesh_identity(*, function_space: Any, mesh_data: Any,
                                 floquet_data: Any) -> dict[str, Any]:
    """Read identity from the actual distributed mesh/tags/V/Floquet objects."""

    msh = mesh_data.mesh
    comm = msh.comm
    topology = msh.topology
    tdim, fdim = topology.dim, topology.dim - 1
    topology.create_connectivity(tdim, 0)
    topology.create_connectivity(fdim, 0)
    cell_vertices = topology.connectivity(tdim, 0)
    facet_vertices = topology.connectivity(fdim, 0)
    owned_cells = int(topology.index_map(tdim).size_local)
    owned_facets = int(topology.index_map(fdim).size_local)
    coordinates = np.asarray(msh.geometry.x)
    geometry_dofmap = np.asarray(msh.geometry.dofmap)
    local_cells = [_entity_key(coordinates[geometry_dofmap[cell]])
                   for cell in range(owned_cells)]
    vertex_to_geometry: dict[int, int] = {}
    local_and_ghost_cells = int(topology.index_map(tdim).size_local
                                + topology.index_map(tdim).num_ghosts)
    for cell in range(local_and_ghost_cells):
        vertices = cell_vertices.links(cell)
        geometry_nodes = geometry_dofmap[cell]
        if len(vertices) != len(geometry_nodes):
            raise RuntimeError("linear mesh vertex/geometry layout mismatch")
        for vertex, node in zip(vertices, geometry_nodes):
            previous = vertex_to_geometry.setdefault(int(vertex), int(node))
            if previous != int(node):
                raise RuntimeError("inconsistent topology-vertex to geometry-node map")
    tag_by_cell = {int(i): int(v) for i, v in
                   zip(np.asarray(mesh_data.cell_tags.indices),
                       np.asarray(mesh_data.cell_tags.values))}
    local_material = [(key, tag_by_cell[cell]) for cell, key in enumerate(local_cells)]
    local_boundary = []
    boundary_counts: dict[int, int] = {}
    for facet, tag in zip(np.asarray(mesh_data.facet_tags.indices),
                          np.asarray(mesh_data.facet_tags.values)):
        facet, tag = int(facet), int(tag)
        if facet >= owned_facets:
            continue
        nodes = [vertex_to_geometry[int(vertex)] for vertex in facet_vertices.links(facet)]
        local_boundary.append((tag, _entity_key(coordinates[nodes])))
        boundary_counts[tag] = boundary_counts.get(tag, 0) + 1
    all_cells = sorted({item for part in comm.allgather(local_cells) for item in part})
    all_material = sorted({item for part in comm.allgather(local_material) for item in part})
    all_boundary = sorted({item for part in comm.allgather(local_boundary) for item in part})
    global_boundary_counts = {
        str(tag): int(comm.allreduce(boundary_counts.get(tag, 0)))
        for tag in sorted({tag for tag, _ in all_boundary})
    }
    points = sorted({_point(point) for cell in all_cells for point in cell})
    axes = {name: sorted({point[index] for point in points})
            for index, name in enumerate(("x", "y", "z"))}
    element = function_space.element.basix_element
    index_map = function_space.dofmap.index_map
    global_dofs = int(index_map.size_global * function_space.dofmap.index_map_bs)
    topology_object = getattr(floquet_data, "phase_independent_topology", None)
    local_blocks = []
    if topology_object is not None:
        for block in topology_object.blocks:
            local_blocks.append({
                "entity_kind": block.entity_kind, "direction": block.kind,
                "slave_geometry": block.slave_entity_geometry_key,
                "master_geometry": block.master_entity_geometry_key,
                "periodic_pair_key": block.periodic_pair_key,
            })
    floquet_blocks = sorted(
        {json.dumps(value, sort_keys=True, separators=(",", ":"))
         for part in comm.allgather(local_blocks) for value in part}
    )
    actual = {
        "schema_version": RUNTIME_SCHEMA, "mpi_ranks": comm.size,
        "global_cell_count": len(all_cells),
        "canonical_cell_geometry_sha256": _sha(all_cells),
        "axis_values_nm": axes,
        "axis_cell_counts": [len(axes[name]) - 1 for name in ("x", "y", "z")],
        "coordinate_axis_sha256": canonical_hash(axes),
        "material_cell_geometry_tag_sha256": _sha(all_material),
        "material_cell_tag_counts": {
            str(tag): sum(value == tag for _, value in all_material)
            for tag in sorted({value for _, value in all_material})
        },
        "boundary_facet_geometry_tag_sha256": _sha(all_boundary),
        "boundary_facet_tag_counts": global_boundary_counts,
        "element": {
            "family_raw": str(element.family), "cell_raw": str(element.cell_type),
            "degree": int(element.degree), "hash": int(element.hash()),
            "map_type": str(element.map_type), "value_shape": list(element.value_shape),
        },
        "global_dof_count": global_dofs,
        "dof_layout_identity_sha256": canonical_hash({
            "global_dof_count": global_dofs, "element_hash": int(element.hash()),
            "cell_geometry": _sha(all_cells),
        }),
        "floquet": {
            "constraint_mode": floquet_data.constraint_mode_resolved,
            "global_constraint_count": int(floquet_data.num_constraints),
            "x_constraint_count": int(floquet_data.num_x_constraints),
            "y_constraint_count": int(floquet_data.num_y_constraints),
            "corner_constraint_count": int(floquet_data.num_corner_constraints),
            "physical_block_count": len(floquet_blocks),
            "physical_entity_identity_sha256": _sha(floquet_blocks),
        },
    }
    return comm.bcast(actual if comm.rank == 0 else None, root=0)


def compare_planned_actual(parameters: Task002ForwardParameters,
                           actual: dict[str, Any]) -> dict[str, Any]:
    planned = planned_runtime_identity(parameters)
    cfg = build_task002_full3d_config(parameters)
    periodic_tags = (cfg.tags.x_min, cfg.tags.x_max, cfg.tags.y_min, cfg.tags.y_max)
    gates = {
        "global_cell_count": actual["global_cell_count"] == planned["global_cell_count"],
        "axis_cell_counts": actual["axis_cell_counts"] == planned["axis_cell_counts"],
        "axis_values": actual["axis_values_nm"] == planned["axis_values_nm"],
        "canonical_cell_geometry": actual["canonical_cell_geometry_sha256"] == planned["canonical_cell_geometry_sha256"],
        "material_cell_tags": actual["material_cell_geometry_tag_sha256"] == planned["material_cell_geometry_tag_sha256"],
        "boundary_facets": actual["boundary_facet_geometry_tag_sha256"] == planned["boundary_facet_geometry_tag_sha256"],
        "periodic_boundary_counts": all(
            actual["boundary_facet_tag_counts"].get(str(tag))
            == planned["periodic_boundary_facet_counts"][str(tag)] for tag in periodic_tags
        ),
        "element_degree": actual["element"]["degree"] == planned["element"]["degree"],
        "element_family": "N1E" in actual["element"]["family_raw"] or "N1curl" in actual["element"]["family_raw"],
        "element_cell": "hexahedron" in actual["element"]["cell_raw"].lower(),
        "global_dof_count": actual["global_dof_count"] == planned["expected_global_dof_count"],
        "floquet_entities_present": actual["floquet"]["physical_block_count"] > 0,
        "floquet_xy_constraints_present": actual["floquet"]["x_constraint_count"] > 0
        and actual["floquet"]["y_constraint_count"] > 0,
    }
    return {"planned": planned, "actual": actual, "gates": gates,
            "pass": all(gates.values())}
