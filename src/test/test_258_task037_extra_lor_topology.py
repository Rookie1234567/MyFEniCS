from __future__ import annotations

import basix
import numpy as np
import pytest

from src.solvers.static_lor_hcurl_transfer import (
    build_affine_lor_parent_topology,
)


_CELL_PERMUTATION_INFO = 0xA5


def _parent_vertices(translation=(0.0, 0.0, 0.0)) -> np.ndarray:
    return basix.geometry(basix.CellType.hexahedron) + np.asarray(
        translation, dtype=np.float64
    )


def _build(degree: int, vertices: np.ndarray, *, cell_id: int, material: int):
    return build_affine_lor_parent_topology(
        vertices,
        degree=degree,
        canonical_cell_id=cell_id,
        material_tag=material,
        cell_permutation=_CELL_PERMUTATION_INFO,
        coordinate_tolerance=1.0e-12,
    )


@pytest.mark.parametrize("degree, expected_edges", ((2, 54), (3, 144)))
def test_single_parent_topology_is_complete_and_deterministic(
    degree: int, expected_edges: int
):
    first = _build(degree, _parent_vertices(), cell_id=17, material=4)
    second = _build(degree, _parent_vertices(), cell_id=17, material=4)

    assert first.degree == degree
    assert first.canonical_cell_id == 17
    assert first.material_tag == 4
    assert first.cell_permutation == _CELL_PERMUTATION_INFO
    assert first.reference_nodes[0] == 0.0
    assert first.reference_nodes[-1] == 1.0
    assert np.all(np.diff(first.reference_nodes) > 0.0)
    assert first.vertices.shape == ((degree + 1) ** 3, 3)
    assert first.cells.shape == (degree**3, 8)
    assert first.edge_keys == tuple(dict.fromkeys(first.edge_keys))
    assert len(first.edge_keys) == expected_edges
    assert first.edge_endpoints.shape == (expected_edges, 2)
    assert first.cell_edge_ids.shape == (degree**3, 12)
    assert np.all(np.abs(first.cell_edge_orientations) == 1)
    assert np.all(
        np.apply_along_axis(lambda row: len(set(row)), 1, first.cells) == 8
    )
    assert all(len(set(face_ids)) == len(face_ids) for face_ids in first.edge_boundary_faces)
    assert all(
        sum(face_id in face_ids for face_ids in first.edge_boundary_faces)
        == 2 * degree * (degree + 1)
        for face_id in range(6)
    )
    assert np.array_equal(first.vertices, second.vertices)
    assert np.array_equal(first.cells, second.cells)
    assert first.vertex_keys == second.vertex_keys
    assert first.edge_keys == second.edge_keys
    assert np.array_equal(first.edge_endpoints, second.edge_endpoints)
    assert first.edge_boundary_faces == second.edge_boundary_faces
    assert np.array_equal(first.cell_edge_ids, second.cell_edge_ids)
    assert np.array_equal(
        first.cell_edge_orientations,
        second.cell_edge_orientations,
    )
    assert not first.vertices.flags.writeable
    assert not first.cells.flags.writeable


@pytest.mark.parametrize("degree", (2, 3))
def test_adjacent_parents_share_only_their_face_edges(degree: int):
    left = _build(degree, _parent_vertices(), cell_id=0, material=10)
    right = _build(
        degree,
        _parent_vertices((1.0, 0.0, 0.0)),
        cell_id=1,
        material=20,
    )
    shared = set(left.edge_keys).intersection(right.edge_keys)
    assert len(shared) == 2 * degree * (degree + 1)
    assert len(set(left.edge_keys).union(right.edge_keys)) == (
        2 * 3 * degree * (degree + 1) ** 2 - len(shared)
    )
    assert left.material_tag == 10
    assert right.material_tag == 20
    assert left.canonical_cell_id != right.canonical_cell_id


def test_positive_reorientation_preserves_keys_and_records_orientation_signs():
    reference = basix.geometry(basix.CellType.hexahedron)
    rotation = np.asarray(
        [[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]]
    )
    reoriented_vertices = reference @ rotation.T + np.asarray([2.0, 3.0, 4.0])
    permutation = 0xA5
    first = build_affine_lor_parent_topology(
        reoriented_vertices,
        degree=2,
        canonical_cell_id=8,
        material_tag=7,
        cell_permutation=permutation,
        coordinate_tolerance=1.0e-12,
    )
    positive_axis_vertices = _parent_vertices((1.0, 2.0, 4.0))
    second = build_affine_lor_parent_topology(
        positive_axis_vertices,
        degree=2,
        canonical_cell_id=8,
        material_tag=7,
        cell_permutation=0,
        coordinate_tolerance=1.0e-12,
    )
    assert set(first.edge_keys) == set(second.edge_keys)
    assert set(first.vertex_keys) == set(second.vertex_keys)
    assert first.cell_permutation == permutation
    assert np.any(first.cell_edge_orientations == -1)
    assert set().union(*first.edge_boundary_faces) == set(range(6))
