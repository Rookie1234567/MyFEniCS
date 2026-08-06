"""Affine lowest-order-refined topology inside one high-order hexahedron.

This module records the ``degree**3`` low-order hexahedra obtained by splitting
one affine parent with degree-dependent Gauss--Lobatto--Legendre nodes.  It is
the topology layer for the Task037 LOR path, not a same-mesh p2/p4 coarse
space, and it does not construct a transfer matrix.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import basix
import numpy as np

from src.geometry.tetra_mesh_audit import (
    canonical_entity_key,
    canonical_point_key,
)


_HEX_EDGES: tuple[tuple[int, int], ...] = (
    (0, 1),
    (0, 2),
    (0, 4),
    (1, 3),
    (1, 5),
    (2, 3),
    (2, 6),
    (3, 7),
    (4, 5),
    (4, 6),
    (5, 7),
    (6, 7),
)

_HEX_BOUNDARY_FACES: tuple[tuple[int, int], ...] = (
    (2, 0),  # Basix face 0: z = 0
    (1, 0),  # Basix face 1: y = 0
    (0, 0),  # Basix face 2: x = 0
    (0, 1),  # Basix face 3: x = 1
    (1, 1),  # Basix face 4: y = 1
    (2, 1),  # Basix face 5: z = 1
)


@dataclass(frozen=True)
class AffineLORParentTopology:
    """Canonical child topology and metadata for one affine parent hexahedron."""

    degree: int
    canonical_cell_id: int
    material_tag: int
    cell_permutation: int
    reference_nodes: np.ndarray
    vertices: np.ndarray
    cells: np.ndarray
    vertex_keys: tuple[tuple[int, int, int], ...]
    edge_keys: tuple[tuple[tuple[int, int, int], ...], ...]
    edge_endpoints: np.ndarray
    edge_boundary_faces: tuple[tuple[int, ...], ...]
    cell_edge_ids: np.ndarray
    cell_edge_orientations: np.ndarray

    def __post_init__(self) -> None:
        for name in (
            "reference_nodes",
            "vertices",
            "cells",
            "edge_endpoints",
            "cell_edge_ids",
            "cell_edge_orientations",
        ):
            array = np.asarray(getattr(self, name)).copy()
            array.setflags(write=False)
            object.__setattr__(self, name, array)


def _gll_nodes(degree: int) -> np.ndarray:
    nodes = np.asarray(
        basix.create_lattice(
            basix.CellType.interval,
            degree,
            basix.LatticeType.gll,
            True,
        ),
        dtype=np.float64,
    ).reshape(-1)
    if nodes.size != degree + 1:
        raise RuntimeError("Basix GLL lattice returned an unexpected node count")
    if abs(float(nodes[0])) > 1.0e-12 or abs(float(nodes[-1] - 1.0)) > 1.0e-12:
        raise RuntimeError("Basix GLL lattice endpoints are not [0, 1]")
    nodes[0] = 0.0
    nodes[-1] = 1.0
    if np.any(np.diff(nodes) <= 0.0):
        raise ValueError("GLL reference nodes must be strictly increasing")
    return nodes


def _validate_parent(
    parent_vertices: np.ndarray,
    coordinate_tolerance: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    vertices = np.asarray(parent_vertices, dtype=np.float64)
    if vertices.shape != (8, 3) or not np.all(np.isfinite(vertices)):
        raise ValueError("parent_vertices must be finite with shape (8, 3)")
    if not np.isfinite(coordinate_tolerance) or coordinate_tolerance <= 0.0:
        raise ValueError("coordinate_tolerance must be finite and positive")

    origin = vertices[0]
    axes = np.asarray(
        (vertices[1] - origin, vertices[2] - origin, vertices[4] - origin),
        dtype=np.float64,
    )
    determinant = float(np.linalg.det(axes))
    if determinant <= max(coordinate_tolerance**3, 1.0e-30):
        raise ValueError("parent hexahedron must have a positive affine volume")
    expected = np.asarray(
        [
            origin,
            origin + axes[0],
            origin + axes[1],
            origin + axes[0] + axes[1],
            origin + axes[2],
            origin + axes[0] + axes[2],
            origin + axes[1] + axes[2],
            origin + axes[0] + axes[1] + axes[2],
        ]
    )
    if not np.allclose(vertices, expected, rtol=0.0, atol=coordinate_tolerance):
        raise ValueError("parent_vertices must describe an affine hexahedron")
    return vertices, origin, axes[0], axes[1], axes[2]


def _grid_vertex_index(i: int, j: int, k: int, node_count: int) -> int:
    return (i * node_count + j) * node_count + k


def _boundary_faces_for_edge(
    first: tuple[int, int, int],
    second: tuple[int, int, int],
    degree: int,
) -> tuple[int, ...]:
    faces: list[int] = []
    for face_id, (axis, side) in enumerate(_HEX_BOUNDARY_FACES):
        boundary_index = degree if side else 0
        if first[axis] == boundary_index and second[axis] == boundary_index:
            faces.append(face_id)
    return tuple(faces)


def build_affine_lor_parent_topology(
    parent_vertices: Iterable[Iterable[float]],
    *,
    degree: int,
    canonical_cell_id: int,
    material_tag: int,
    cell_permutation: int,
    coordinate_tolerance: float,
) -> AffineLORParentTopology:
    """Build the deterministic lowest-order refinement of one affine hexahedron.

    ``parent_vertices`` use Basix hexahedron vertex ordering.  The returned
    child cells use the same local ordering, while every child edge is mapped
    to one canonical physical endpoint key and an orientation sign.  This
    function records topology only; it does not create ``T``/``T^H`` or a
    coarse operator.
    """

    if not isinstance(degree, (int, np.integer)) or isinstance(degree, bool):
        raise ValueError("degree must be an integer")
    degree = int(degree)
    if degree < 1:
        raise ValueError("degree must be positive")
    if not isinstance(material_tag, (int, np.integer)) or isinstance(
        material_tag, bool
    ):
        raise ValueError("material_tag must be an integer")
    if not isinstance(cell_permutation, (int, np.integer)) or isinstance(
        cell_permutation, bool
    ):
        raise ValueError("cell_permutation must be an integer bitfield")
    material_tag = int(material_tag)
    permutation = int(cell_permutation)

    _vertices, origin, axis_x, axis_y, axis_z = _validate_parent(
        np.asarray(parent_vertices, dtype=np.float64),
        float(coordinate_tolerance),
    )
    reference_nodes = _gll_nodes(degree)
    node_count = degree + 1
    refined_vertices = np.empty((node_count**3, 3), dtype=np.float64)
    for i, reference_x in enumerate(reference_nodes):
        for j, reference_y in enumerate(reference_nodes):
            for k, reference_z in enumerate(reference_nodes):
                refined_vertices[_grid_vertex_index(i, j, k, node_count)] = (
                    origin
                    + reference_x * axis_x
                    + reference_y * axis_y
                    + reference_z * axis_z
                )

    vertex_keys = tuple(
        canonical_point_key(point, float(coordinate_tolerance))
        for point in refined_vertices
    )
    if len(set(vertex_keys)) != len(vertex_keys):
        raise ValueError("refined vertices have duplicate canonical point keys")

    cell_rows: list[tuple[int, ...]] = []
    cell_grid_rows: list[tuple[tuple[int, int, int], ...]] = []
    for i in range(degree):
        for j in range(degree):
            for k in range(degree):
                local_grid = (
                    (i, j, k),
                    (i + 1, j, k),
                    (i, j + 1, k),
                    (i + 1, j + 1, k),
                    (i, j, k + 1),
                    (i + 1, j, k + 1),
                    (i, j + 1, k + 1),
                    (i + 1, j + 1, k + 1),
                )
                cell_grid_rows.append(local_grid)
                cell_rows.append(
                    tuple(
                        _grid_vertex_index(*grid_vertex, node_count)
                        for grid_vertex in local_grid
                    )
                )

    edge_id_by_key: dict[tuple[tuple[int, int, int], ...], int] = {}
    edge_keys: list[tuple[tuple[int, int, int], ...]] = []
    edge_endpoints: list[tuple[int, int]] = []
    edge_boundary_faces: list[set[int]] = []
    cell_edge_ids = np.empty((len(cell_rows), len(_HEX_EDGES)), dtype=np.int64)
    cell_edge_orientations = np.empty_like(cell_edge_ids)

    for cell_index, (cell_row, grid_row) in enumerate(
        zip(cell_rows, cell_grid_rows, strict=True)
    ):
        for local_edge, (first_local, second_local) in enumerate(_HEX_EDGES):
            first_vertex = cell_row[first_local]
            second_vertex = cell_row[second_local]
            first_key = vertex_keys[first_vertex]
            second_key = vertex_keys[second_vertex]
            edge_key = canonical_entity_key(
                refined_vertices[[first_vertex, second_vertex]],
                float(coordinate_tolerance),
            )
            edge_id = edge_id_by_key.get(edge_key)
            if edge_id is None:
                edge_id = len(edge_keys)
                edge_id_by_key[edge_key] = edge_id
                edge_keys.append(edge_key)
                if first_key <= second_key:
                    edge_endpoints.append((first_vertex, second_vertex))
                else:
                    edge_endpoints.append((second_vertex, first_vertex))
                edge_boundary_faces.append(set())
            canonical_endpoints = (
                vertex_keys[edge_endpoints[edge_id][0]],
                vertex_keys[edge_endpoints[edge_id][1]],
            )
            cell_edge_ids[cell_index, local_edge] = edge_id
            cell_edge_orientations[cell_index, local_edge] = (
                1 if (first_key, second_key) == canonical_endpoints else -1
            )
            edge_boundary_faces[edge_id].update(
                _boundary_faces_for_edge(
                    grid_row[first_local],
                    grid_row[second_local],
                    degree,
                )
            )

    return AffineLORParentTopology(
        degree=degree,
        canonical_cell_id=int(canonical_cell_id),
        material_tag=material_tag,
        cell_permutation=permutation,
        reference_nodes=reference_nodes,
        vertices=refined_vertices,
        cells=np.asarray(cell_rows, dtype=np.int64),
        vertex_keys=vertex_keys,
        edge_keys=tuple(edge_keys),
        edge_endpoints=np.asarray(edge_endpoints, dtype=np.int64),
        edge_boundary_faces=tuple(
            tuple(sorted(faces)) for faces in edge_boundary_faces
        ),
        cell_edge_ids=cell_edge_ids,
        cell_edge_orientations=cell_edge_orientations,
    )
