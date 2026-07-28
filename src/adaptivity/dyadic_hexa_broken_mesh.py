"""DOLFINx carrier and geometry authority for nonmatching dyadic hexahedra.

DOLFINx 0.10 cannot refine hexahedra and does not recognize a coarse face
covered by four fine faces as one topological interface.  Task035d therefore
uses two deliberately separate layers:

* :class:`BalancedDyadicHexForest` is the physical topology authority; and
* this module creates a Q1 affine-hexa DOLFINx carrier for compiled cell
  kernels, cell orientation, physical boundary integrals, and field storage.

Conforming vertices/facets are shared.  A hanging interface remains
topologically broken, so DOLFINx reports its one coarse and four fine facets as
exterior.  The builder proves that every such artificial exterior facet is
explained by the forest hanging catalog and never assigns it a physical
boundary marker.

This is a component authority.  It does not yet build H(curl) hanging/Floquet
constraints and grants no PDE accuracy credit.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

from basix.ufl import element
from dolfinx import default_real_type, graph, mesh
from mpi4py import MPI
import numpy as np
import ufl

from .dyadic_hexa_refinement import (
    BalancedDyadicHexForest,
    Box,
    DyadicHexCell,
)


FaceGeometryKey = tuple[int, float, float, float, float, float]
_BOUNDARY_MARKERS = MappingProxyType(
    {
        "x_lower": 1,
        "x_upper": 2,
        "y_lower": 3,
        "y_upper": 4,
        "z_lower": 5,
        "z_upper": 6,
    }
)
_ROUND_DIGITS = 12


def _round(value: float) -> float:
    return round(float(value), _ROUND_DIGITS)


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def _corners(box: Box) -> tuple[tuple[float, float, float], ...]:
    return tuple(
        (
            box[3] if dx else box[0],
            box[4] if dy else box[1],
            box[5] if dz else box[2],
        )
        for dz in (0, 1)
        for dy in (0, 1)
        for dx in (0, 1)
    )


def _face_geometry_key_from_box(
    box: Box,
    *,
    axis: int,
    side: int,
) -> FaceGeometryKey:
    axis = int(axis)
    side = int(side)
    if axis not in {0, 1, 2} or side not in {0, 1}:
        raise ValueError("hexa face needs axis in [0,2] and side in [0,1]")
    tangential = tuple(candidate for candidate in range(3) if candidate != axis)
    plane = box[axis + 3] if side else box[axis]
    return (
        axis,
        _round(plane),
        _round(box[tangential[0]]),
        _round(box[tangential[0] + 3]),
        _round(box[tangential[1]]),
        _round(box[tangential[1] + 3]),
    )


def _face_geometry_key_from_points(
    points: np.ndarray,
    *,
    tolerance: float,
) -> FaceGeometryKey:
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] < 3:
        raise ValueError("facet points must have three coordinates")
    fixed = [
        axis
        for axis in range(3)
        if float(np.ptp(points[:, axis])) <= tolerance
    ]
    if len(fixed) != 1:
        raise RuntimeError("carrier facet is not axis aligned")
    axis = fixed[0]
    tangential = tuple(candidate for candidate in range(3) if candidate != axis)
    return (
        axis,
        _round(float(np.mean(points[:, axis]))),
        _round(float(np.min(points[:, tangential[0]]))),
        _round(float(np.max(points[:, tangential[0]]))),
        _round(float(np.min(points[:, tangential[1]]))),
        _round(float(np.max(points[:, tangential[1]]))),
    )


def _face_area(key: FaceGeometryKey) -> float:
    return float((key[3] - key[2]) * (key[5] - key[4]))


def _boundary_label(
    key: FaceGeometryKey,
    bounds: Box,
    *,
    tolerance: float,
) -> str | None:
    axis = int(key[0])
    plane = float(key[1])
    if abs(plane - bounds[axis]) <= tolerance:
        return ("x", "y", "z")[axis] + "_lower"
    if abs(plane - bounds[axis + 3]) <= tolerance:
        return ("x", "y", "z")[axis] + "_upper"
    return None


def _hanging_artificial_face_keys(
    forest: BalancedDyadicHexForest,
) -> tuple[FaceGeometryKey, ...]:
    cells = forest.leaf_by_key
    result: list[FaceGeometryKey] = []
    for patch in forest.hanging_faces:
        coarse = cells[patch.coarse]
        coarse_key = _face_geometry_key_from_box(
            coarse.box,
            axis=patch.axis,
            side=patch.side,
        )
        result.append(coarse_key)
        plane = coarse_key[1]
        for fine_key in patch.fine:
            fine = cells[fine_key]
            if abs(fine.box[patch.axis] - plane) <= 1.0e-11:
                fine_side = 0
            elif abs(fine.box[patch.axis + 3] - plane) <= 1.0e-11:
                fine_side = 1
            else:
                raise RuntimeError("hanging fine cell does not touch coarse plane")
            result.append(
                _face_geometry_key_from_box(
                    fine.box,
                    axis=patch.axis,
                    side=fine_side,
                )
            )
    if len(set(result)) != len(result):
        raise RuntimeError("hanging artificial facet catalog is not unique")
    return tuple(sorted(result))


def _canonical_vertex_catalog(
    leaves: tuple[DyadicHexCell, ...],
) -> tuple[
    tuple[tuple[float, float, float], ...],
    tuple[tuple[int, ...], ...],
]:
    point_keys = tuple(
        sorted(
            {
                tuple(map(_round, point))
                for cell in leaves
                for point in _corners(cell.box)
            }
        )
    )
    point_index = {point: index for index, point in enumerate(point_keys)}
    connectivity = tuple(
        tuple(point_index[tuple(map(_round, point))] for point in _corners(cell.box))
        for cell in leaves
    )
    return point_keys, connectivity


def _keep_input_cell_owners(comm: MPI.Intracomm):
    def partition(
        _comm,
        num_partitions: int,
        adjacency,
        _ghost_mode: bool,
    ):
        if int(num_partitions) != int(comm.size):
            raise RuntimeError("carrier partition count differs from communicator")
        destinations = np.full(
            (int(adjacency.num_nodes), 1),
            int(comm.rank),
            dtype=np.int32,
        )
        return graph.adjacencylist(destinations)._cpp_object

    return mesh.create_cell_partitioner(
        partition,
        mesh.GhostMode.shared_facet,
    )


@dataclass(frozen=True)
class BrokenDyadicHexCarrier:
    """A broken DOLFINx mesh bound back to the canonical forest leaves."""

    mesh: mesh.Mesh
    cell_tags: mesh.MeshTags
    physical_boundary_tags: mesh.MeshTags
    boundary_markers: Mapping[str, int]
    canonical_leaf_by_local_cell: np.ndarray
    audit: Mapping[str, Any]


def build_broken_dyadic_hexa_carrier(
    forest: BalancedDyadicHexForest,
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    boundary_markers: Mapping[str, int] | None = None,
) -> BrokenDyadicHexCarrier:
    """Build and fully classify a partition-stable broken-hexa carrier."""

    if forest.audit["pass"] is not True:
        raise ValueError("dyadic forest must pass before carrier construction")
    markers = dict(
        _BOUNDARY_MARKERS
        if boundary_markers is None
        else boundary_markers
    )
    if set(markers) != set(_BOUNDARY_MARKERS):
        raise ValueError(
            "broken-hexa boundary markers must define exactly "
            f"{sorted(_BOUNDARY_MARKERS)}"
        )
    markers = {str(label): int(value) for label, value in markers.items()}
    if len(set(markers.values())) != len(markers):
        raise ValueError("broken-hexa physical boundary markers must be unique")
    leaves = tuple(forest.leaves)
    point_keys, connectivity = _canonical_vertex_catalog(leaves)
    leaf_count = len(leaves)
    start = leaf_count * comm.rank // comm.size
    stop = leaf_count * (comm.rank + 1) // comm.size
    local_cells = np.asarray(
        connectivity[start:stop],
        dtype=np.int64,
    ).reshape(-1, 8)
    points = np.asarray(point_keys, dtype=default_real_type)
    coordinate_element = element(
        "Lagrange",
        "hexahedron",
        1,
        shape=(3,),
        dtype=default_real_type,
    )
    msh = mesh.create_mesh(
        comm,
        local_cells,
        ufl.Mesh(coordinate_element),
        points,
        partitioner=_keep_input_cell_owners(comm),
    )
    tdim = int(msh.topology.dim)
    fdim = tdim - 1
    msh.topology.create_entity_permutations()
    cell_map = msh.topology.index_map(tdim)
    owned_cells = int(cell_map.size_local)
    local_cells_with_ghosts = owned_cells + int(cell_map.num_ghosts)
    original = np.asarray(
        msh.topology.original_cell_index,
        dtype=np.int64,
    )
    if original.shape != (local_cells_with_ghosts,):
        raise RuntimeError("carrier original-cell crosswalk is incomplete")
    if np.any(original < 0) or np.any(original >= leaf_count):
        raise RuntimeError("carrier original-cell index is outside forest")

    local_cell_indices = np.arange(
        local_cells_with_ghosts,
        dtype=np.int32,
    )
    cell_geometry = mesh.entities_to_geometry(
        msh,
        tdim,
        local_cell_indices,
        permute=True,
    )
    geometry_box_failures: list[int] = []
    for local_cell, (canonical, dofs) in enumerate(
        zip(original, cell_geometry, strict=True)
    ):
        coordinates = np.asarray(msh.geometry.x[np.asarray(dofs), :3])
        observed = tuple(
            map(
                _round,
                (
                    *np.min(coordinates, axis=0),
                    *np.max(coordinates, axis=0),
                ),
            )
        )
        if observed != leaves[int(canonical)].box:
            geometry_box_failures.append(local_cell)
    if geometry_box_failures:
        raise RuntimeError(
            "carrier cell geometry differs from canonical forest: "
            f"{geometry_box_failures[:8]}"
        )

    owned_indices = np.arange(owned_cells, dtype=np.int32)
    owned_original = original[:owned_cells]
    cell_values = np.asarray(
        [
            leaves[int(canonical)].material_tag
            for canonical in owned_original
        ],
        dtype=np.int32,
    )
    cell_tags = mesh.meshtags(
        msh,
        tdim,
        owned_indices,
        cell_values,
    )

    msh.topology.create_connectivity(fdim, tdim)
    exterior = np.asarray(
        mesh.exterior_facet_indices(msh.topology),
        dtype=np.int32,
    )
    facet_map = msh.topology.index_map(fdim)
    owned_exterior = exterior[exterior < int(facet_map.size_local)]
    facet_geometry = mesh.entities_to_geometry(
        msh,
        fdim,
        owned_exterior,
        permute=True,
    )
    extent = max(
        forest.domain_bounds[axis + 3] - forest.domain_bounds[axis]
        for axis in range(3)
    )
    tolerance = max(float(extent), 1.0) * 1.0e-11
    local_physical: list[tuple[FaceGeometryKey, str, int]] = []
    local_artificial: list[FaceGeometryKey] = []
    for facet, dofs in zip(owned_exterior, facet_geometry, strict=True):
        key = _face_geometry_key_from_points(
            msh.geometry.x[np.asarray(dofs), :3],
            tolerance=tolerance,
        )
        label = _boundary_label(
            key,
            forest.domain_bounds,
            tolerance=tolerance,
        )
        if label is None:
            local_artificial.append(key)
        else:
            local_physical.append((key, label, int(facet)))

    physical_rows = [
        row
        for packet in comm.allgather(
            tuple((key, label) for key, label, _facet in local_physical)
        )
        for row in packet
    ]
    artificial_rows = [
        row
        for packet in comm.allgather(tuple(local_artificial))
        for row in packet
    ]
    if len(set(key for key, _label in physical_rows)) != len(physical_rows):
        raise RuntimeError("physical exterior facets have duplicate owners")
    if len(set(artificial_rows)) != len(artificial_rows):
        raise RuntimeError("artificial exterior facets have duplicate owners")
    expected_artificial = _hanging_artificial_face_keys(forest)
    actual_artificial = tuple(sorted(artificial_rows))
    if actual_artificial != expected_artificial:
        missing = sorted(set(expected_artificial) - set(actual_artificial))
        extra = sorted(set(actual_artificial) - set(expected_artificial))
        raise RuntimeError(
            "topological exterior is not explained by physical/hanging "
            f"catalogs: missing={missing[:4]}, extra={extra[:4]}"
        )

    boundary_indices = np.asarray(
        [facet for _key, _label, facet in local_physical],
        dtype=np.int32,
    )
    boundary_values = np.asarray(
        [markers[label] for _key, label, _facet in local_physical],
        dtype=np.int32,
    )
    order = np.argsort(boundary_indices)
    physical_boundary_tags = mesh.meshtags(
        msh,
        fdim,
        boundary_indices[order],
        boundary_values[order],
    )

    owned_packets = comm.allgather(tuple(map(int, owned_original)))
    flat_owned = tuple(value for packet in owned_packets for value in packet)
    if len(flat_owned) != leaf_count or set(flat_owned) != set(range(leaf_count)):
        raise RuntimeError("carrier owned-cell partition does not cover forest once")
    if len(set(flat_owned)) != len(flat_owned):
        raise RuntimeError("carrier owned-cell partition overlaps")

    owner_by_leaf = {
        canonical: rank
        for rank, packet in enumerate(owned_packets)
        for canonical in packet
    }
    cross_rank_hanging = 0
    for patch in forest.hanging_faces:
        members = (patch.coarse, *patch.fine)
        owners = {
            owner_by_leaf[leaves.index(forest.leaf_by_key[key])]
            for key in members
        }
        cross_rank_hanging += len(owners) > 1

    physical_area = sum(_face_area(key) for key, _label in physical_rows)
    bounds = forest.domain_bounds
    widths = tuple(bounds[axis + 3] - bounds[axis] for axis in range(3))
    expected_area = 2.0 * (
        widths[0] * widths[1]
        + widths[0] * widths[2]
        + widths[1] * widths[2]
    )
    global_topological_exterior = int(
        comm.allreduce(len(owned_exterior), op=MPI.SUM)
    )
    topological_facets = int(facet_map.size_global)
    geometry_vertices = int(msh.geometry.index_map().size_global)
    checks = {
        "forest_authority_pass": forest.audit["pass"] is True,
        "owned_cells_cover_forest_once": len(flat_owned) == leaf_count,
        "original_cell_crosswalk_matches_geometry": not geometry_box_failures,
        "canonical_vertex_count_matches_carrier": (
            geometry_vertices == len(point_keys)
        ),
        "all_artificial_exterior_is_hanging": (
            actual_artificial == expected_artificial
        ),
        "artificial_exterior_count_is_five_per_patch": (
            len(actual_artificial) == 5 * len(forest.hanging_faces)
        ),
        "physical_boundary_area": abs(physical_area - expected_area)
        <= 1.0e-10 * max(expected_area, 1.0),
        "physical_and_artificial_exterior_partition": (
            global_topological_exterior
            == len(physical_rows) + len(actual_artificial)
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError(f"broken-hexa carrier audit failed: {failures}")
    audit = MappingProxyType(
        {
            "schema_version": "task035d.broken-dyadic-hexa-carrier.v1",
            "status": "broken_dyadic_hexa_carrier_component_pass",
            "pass": True,
            "mpi_size": int(comm.size),
            "dolfinx_cell_type": str(msh.topology.cell_type),
            "geometry_degree": 1,
            "axis_aligned_affine_hexahedra": True,
            "canonical_leaf_count": leaf_count,
            "canonical_vertex_count": len(point_keys),
            "carrier_global_cell_count": int(cell_map.size_global),
            "carrier_global_vertex_count": geometry_vertices,
            "carrier_global_topological_facet_count": topological_facets,
            "topological_exterior_facet_count": global_topological_exterior,
            "physical_exterior_facet_count": len(physical_rows),
            "artificial_hanging_exterior_facet_count": len(
                actual_artificial
            ),
            "hanging_patch_count": len(forest.hanging_faces),
            "cross_rank_hanging_patch_count": int(cross_rank_hanging),
            "physical_boundary_area": physical_area,
            "expected_boundary_area": expected_area,
            "owned_cell_counts_by_rank": [
                len(packet) for packet in owned_packets
            ],
            "ghost_cell_counts_by_rank": comm.allgather(
                int(cell_map.num_ghosts)
            ),
            "leaf_catalog_sha256": str(
                forest.audit["leaf_catalog_sha256"]
            ),
            "canonical_connectivity_sha256": _json_sha256(connectivity),
            "physical_facet_catalog_sha256": _json_sha256(
                sorted(physical_rows)
            ),
            "artificial_facet_catalog_sha256": _json_sha256(
                actual_artificial
            ),
            "material_catalog_sha256": _json_sha256(
                [
                    (cell.key.to_dict(), cell.material_tag)
                    for cell in leaves
                ]
            ),
            "boundary_markers": dict(markers),
            "checks": checks,
            "failures": failures,
            "hanging_relation_source": "global_geometry_catalog",
            "dolfinx_shared_facet_is_not_hanging_authority": True,
            "hcurl_hanging_constraints_built": False,
            "mpi_constraint_ownership_qualified": False,
            "pde_accuracy_credit": False,
            "ordinary_default_changed": False,
        }
    )
    canonical_leaf_by_local_cell = np.ascontiguousarray(original)
    canonical_leaf_by_local_cell.setflags(write=False)
    return BrokenDyadicHexCarrier(
        mesh=msh,
        cell_tags=cell_tags,
        physical_boundary_tags=physical_boundary_tags,
        boundary_markers=MappingProxyType(markers),
        canonical_leaf_by_local_cell=canonical_leaf_by_local_cell,
        audit=audit,
    )


__all__ = [
    "BrokenDyadicHexCarrier",
    "FaceGeometryKey",
    "build_broken_dyadic_hexa_carrier",
]
