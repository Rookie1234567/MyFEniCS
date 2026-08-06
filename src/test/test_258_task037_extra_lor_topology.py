from __future__ import annotations

import basix
import numpy as np
import pytest

from src.solvers.static_lor_hcurl_transfer import (
    _reference_transfer_data,
    build_affine_lor_parent_topology,
    build_lor_parent_transfer,
)


_CELL_PERMUTATION_INFO = 0xA5
_EDGE_REFLECTION_INFO = 1 << (18 + 1)


def _parent_vertices(translation=(0.0, 0.0, 0.0)) -> np.ndarray:
    return basix.geometry(basix.CellType.hexahedron) + np.asarray(
        translation, dtype=np.float64
    )


def _build(
    degree: int,
    vertices: np.ndarray,
    *,
    cell_id: int,
    material: int,
    cell_permutation: int = 0,
):
    return build_affine_lor_parent_topology(
        vertices,
        degree=degree,
        canonical_cell_id=cell_id,
        material_tag=material,
        cell_permutation=cell_permutation,
        coordinate_tolerance=1.0e-12,
    )


def _positive_reference_edges(topology):
    degree = topology.degree
    node_count = degree + 1

    def index(i, j, k):
        return (i * node_count + j) * node_count + k

    corners = topology.vertices[
        [
            index(0, 0, 0),
            index(degree, 0, 0),
            index(0, degree, 0),
            index(0, 0, degree),
        ]
    ]
    origin = corners[0]
    axes = np.column_stack(
        (corners[1] - origin, corners[2] - origin, corners[3] - origin)
    )
    signs = np.zeros(len(topology.edge_keys), dtype=np.int8)
    for edge_ids, edge_signs in zip(
        topology.cell_edge_ids,
        topology.cell_edge_orientations,
        strict=True,
    ):
        for edge_id, edge_sign in zip(edge_ids, edge_signs, strict=True):
            if signs[int(edge_id)] == 0:
                signs[int(edge_id)] = int(edge_sign)
    physical = topology.vertices[topology.edge_endpoints]
    reference = np.asarray(
        [np.linalg.solve(axes, (pair - origin).T).T for pair in physical]
    )
    positive = reference.copy()
    for edge_id, sign in enumerate(signs):
        if sign < 0:
            positive[edge_id] = positive[edge_id, ::-1]
    return positive[:, 0], positive[:, 1], signs


def _independent_moment_matrix(topology) -> np.ndarray:
    degree = int(topology.degree)
    element = basix.ufl.element("N1curl", "hexahedron", degree).basix_element
    points, weights = basix.make_quadrature(
        basix.CellType.interval,
        2 * degree + 2,
    )
    points = np.asarray(points, dtype=np.float64).reshape(-1)
    weights = np.asarray(weights, dtype=np.float64).reshape(-1)
    starts, ends, _signs = _positive_reference_edges(topology)
    matrix = np.zeros((len(topology.edge_keys), element.dim), dtype=np.complex128)
    for row, (start, end) in enumerate(zip(starts, ends, strict=True)):
        tangent = end - start
        edge_points = start + points[:, None] * tangent
        values = np.asarray(element.tabulate(0, edge_points)[0])
        axis = int(np.argmax(np.abs(tangent)))
        matrix[row] = np.einsum(
            "q,qm->m",
            weights * tangent[axis],
            values[:, :, axis],
        )
    return matrix


def _relative(observed: np.ndarray, expected: np.ndarray) -> float:
    return float(
        np.linalg.norm(observed - expected)
        / max(float(np.linalg.norm(expected)), np.finfo(float).tiny)
    )


def _line_integrals(topology, field) -> np.ndarray:
    starts, ends, _signs = _positive_reference_edges(topology)
    values = []
    for start, end in zip(starts, ends, strict=True):
        tangent = end - start
        axis = int(np.argmax(np.abs(tangent)))
        values.append(
            0.5
            * (field(start)[axis] + field(end)[axis])
            * tangent[axis]
        )
    return np.asarray(values, dtype=np.complex128)


def _interpolated_coefficients(degree: int, field) -> np.ndarray:
    element = basix.ufl.element("N1curl", "hexahedron", degree).basix_element
    values = np.asarray([field(point) for point in element.points])
    return np.asarray(
        element.interpolation_matrix @ values.T.reshape(-1),
        dtype=np.complex128,
    )


@pytest.mark.parametrize("degree, expected_edges", ((2, 54), (3, 144)))
def test_single_parent_topology_is_complete_and_deterministic(
    degree: int, expected_edges: int
):
    first = _build(
        degree,
        _parent_vertices(),
        cell_id=17,
        material=4,
        cell_permutation=_CELL_PERMUTATION_INFO,
    )
    second = _build(
        degree,
        _parent_vertices(),
        cell_id=17,
        material=4,
        cell_permutation=_CELL_PERMUTATION_INFO,
    )

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


@pytest.mark.parametrize("degree", (2, 3))
def test_lor_parent_transfer_dimension_inverse_and_random_action(degree: int):
    topology = _build(
        degree,
        _parent_vertices(),
        cell_id=3,
        material=2,
    )
    transfer = build_lor_parent_transfer(topology)
    moment_matrix = _independent_moment_matrix(topology)
    matrix = transfer._forward.toarray()
    rng = np.random.default_rng(2580 + degree)
    reference_high = rng.standard_normal(transfer.audit["high_dim"]) + 1j * rng.standard_normal(
        transfer.audit["high_dim"]
    )
    lor_values = moment_matrix @ reference_high
    observed = transfer.apply(lor_values)

    assert moment_matrix.shape == (
        transfer.audit["lor_edges"],
        transfer.audit["high_dim"],
    )
    assert np.linalg.matrix_rank(moment_matrix) == transfer.audit["high_dim"]
    assert np.all(np.linalg.norm(moment_matrix, axis=1) > 0.0)
    assert np.all(np.linalg.norm(moment_matrix, axis=0) > 0.0)
    assert _relative(observed, reference_high) <= 1.0e-11
    assert _relative(moment_matrix @ matrix, np.eye(transfer.audit["high_dim"])) <= 1.0e-11
    assert _relative(matrix @ moment_matrix, np.eye(transfer.audit["lor_edges"])) <= 1.0e-11
    assert transfer.audit["left_inverse_error"] <= 1.0e-11
    assert transfer.audit["right_inverse_error"] <= 1.0e-11
    assert transfer.audit["T_nnz"] == transfer._forward.nnz
    assert transfer.audit["T_payload_bytes"] > 0


@pytest.mark.parametrize("degree", (2, 3))
def test_lor_parent_transfer_matches_constant_and_curl_compatible_affine_fields(
    degree: int,
):
    topology = _build(
        degree,
        _parent_vertices(),
        cell_id=4,
        material=2,
    )
    transfer = build_lor_parent_transfer(topology)

    def constant(point):
        del point
        return np.asarray([0.7, -0.2, 1.1], dtype=np.complex128)

    def affine(point):
        x, y, z = point
        return np.asarray(
            [
                1.0 + 2.0 * y - 0.5 * z,
                -0.2 + 0.75 * x + 0.3 * z,
                0.4 - 0.6 * x + 0.9 * y,
            ],
            dtype=np.complex128,
        )

    for field in (constant, affine):
        expected = _interpolated_coefficients(degree, field)
        observed = transfer.apply(_line_integrals(topology, field))
        assert _relative(observed, expected) <= 1.0e-11


@pytest.mark.parametrize("degree", (2, 3))
def test_lor_parent_transfer_adjoint_and_cell_orientation(degree: int):
    topology = _build(
        degree,
        _parent_vertices(),
        cell_id=5,
        material=2,
    )
    transfer = build_lor_parent_transfer(topology)
    rng = np.random.default_rng(2581 + degree)
    x = rng.standard_normal(transfer.audit["lor_edges"]) + 1j * rng.standard_normal(
        transfer.audit["lor_edges"]
    )
    y = rng.standard_normal(transfer.audit["high_dim"]) + 1j * rng.standard_normal(
        transfer.audit["high_dim"]
    )
    left = np.vdot(transfer.apply(x), y)
    right = np.vdot(x, transfer.apply_adjoint(y))
    assert abs(left - right) / max(abs(left), abs(right), 1.0) <= 1.0e-11

    oriented_topology = build_affine_lor_parent_topology(
        _parent_vertices(),
        degree=degree,
        canonical_cell_id=5,
        material_tag=2,
        cell_permutation=_EDGE_REFLECTION_INFO,
        coordinate_tolerance=1.0e-12,
    )
    oriented_transfer = build_lor_parent_transfer(oriented_topology)
    moment_matrix = _independent_moment_matrix(topology)
    reference_high = rng.standard_normal(transfer.audit["high_dim"])
    lor_values = moment_matrix @ reference_high
    expected = reference_high.copy()
    element = basix.ufl.element("N1curl", "hexahedron", degree).basix_element
    element.T_apply(expected, 1, _EDGE_REFLECTION_INFO)
    observed = oriented_transfer.apply(lor_values)
    assert _relative(observed, expected) <= 1.0e-11
    assert np.linalg.norm(expected - reference_high) > 1.0e-8
    assert oriented_transfer.audit["cell_permutation"] == _EDGE_REFLECTION_INFO

    rotation = np.asarray(
        [[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]]
    )
    reoriented_vertices = (
        basix.geometry(basix.CellType.hexahedron) @ rotation.T
        + np.asarray([2.0, 3.0, 4.0])
    )
    reoriented_topology = build_affine_lor_parent_topology(
        reoriented_vertices,
        degree=degree,
        canonical_cell_id=5,
        material_tag=2,
        cell_permutation=0,
        coordinate_tolerance=1.0e-12,
    )
    reoriented_transfer = build_lor_parent_transfer(reoriented_topology)
    reoriented_moments = _independent_moment_matrix(reoriented_topology)
    starts, ends, signs = _positive_reference_edges(reoriented_topology)
    del starts, ends
    assert np.any(signs == -1)
    reoriented_lor = signs * (reoriented_moments @ reference_high)
    assert _relative(
        reoriented_transfer.apply(reoriented_lor),
        reference_high,
    ) <= 1.0e-11


def test_lor_parent_transfer_reference_cache_and_actions_are_deterministic():
    _reference_transfer_data.cache_clear()
    topology = _build(
        2,
        _parent_vertices(),
        cell_id=6,
        material=2,
    )
    first = build_lor_parent_transfer(topology)
    after_first = _reference_transfer_data.cache_info()
    second = build_lor_parent_transfer(topology)
    after_second = _reference_transfer_data.cache_info()
    values = np.arange(first.audit["lor_edges"], dtype=np.complex128) + 0.25j

    assert after_first.misses == 1
    assert after_second.hits >= 1
    assert first.audit == second.audit
    assert np.array_equal(first._forward.data, second._forward.data)
    assert np.array_equal(first._forward.indices, second._forward.indices)
    assert np.array_equal(first._forward.indptr, second._forward.indptr)
    assert np.array_equal(first.apply(values), second.apply(values))
