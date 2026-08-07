from __future__ import annotations

import basix
import numpy as np
import pytest
import scipy.sparse as sp

from src.solvers.static_lor_hcurl_auxiliary import (
    build_lor_hcurl_auxiliary_space,
)
from src.solvers.static_lor_hcurl_transfer import (
    build_affine_lor_parent_topology,
    build_lor_slab_edge_space,
)
from src.test.test_259_task037_extra_lor_slab_edges import (
    _empty_floquet,
    _synthetic_floquet,
)


_TOLERANCE = 1.0e-12
_COMMUTING_TOLERANCE = 1.0e-12


def _parent_vertices(translation=(0.0, 0.0, 0.0)) -> np.ndarray:
    return basix.geometry(basix.CellType.hexahedron) + np.asarray(
        translation,
        dtype=np.float64,
    )


def _topology(degree: int, cell_id: int, translation=(0.0, 0.0, 0.0)):
    return build_affine_lor_parent_topology(
        _parent_vertices(translation),
        degree=degree,
        canonical_cell_id=cell_id,
        material_tag=cell_id + 3,
        cell_permutation=0,
        coordinate_tolerance=_TOLERANCE,
    )


def _relative_sparse(observed, expected) -> float:
    difference = (observed - expected).tocsr()
    return float(
        np.linalg.norm(difference.data)
        / max(np.linalg.norm(expected.data), np.finfo(float).tiny)
    )


def _local_incidence(topology):
    vertex_index = {key: index for index, key in enumerate(topology.vertex_keys)}
    rows = []
    columns = []
    values = []
    for row, (first, second) in enumerate(topology.edge_keys):
        rows.extend((row, row))
        columns.extend((vertex_index[first], vertex_index[second]))
        values.extend((-1.0, 1.0))
    return sp.csr_matrix(
        (values, (rows, columns)),
        shape=(len(topology.edge_keys), len(topology.vertex_keys)),
        dtype=np.complex128,
    )


def _row_entry(matrix, row: int):
    start = int(matrix.indptr[row])
    end = int(matrix.indptr[row + 1])
    assert end - start == 1
    return int(matrix.indices[start]), complex(matrix.data[start])


@pytest.mark.parametrize("degree", (2, 3))
def test_vertex_edge_spaces_are_deduplicated_deterministic_and_commuting(degree):
    left = _topology(degree, 10)
    right = _topology(degree, 2, (1.0, 0.0, 0.0))
    edge_space = build_lor_slab_edge_space(
        [right, left],
        _empty_floquet(degree),
        phase_x=1.0 + 0.0j,
        phase_y=1.0 + 0.0j,
    )
    auxiliary = build_lor_hcurl_auxiliary_space([left, right], edge_space)

    expected_vertices = (2 * degree + 1) * (degree + 1) ** 2
    expected_shared_edges = 2 * degree * (degree + 1)
    assert auxiliary.parent_ids == (2, 10)
    assert auxiliary.audit["physical_vertex_count"] == expected_vertices
    assert auxiliary.audit["active_vertex_count"] == expected_vertices
    assert len(edge_space.active_edge_keys) == (
        2 * len(left.edge_keys) - expected_shared_edges
    )
    assert len(auxiliary.active_vertex_keys) == len(
        set(auxiliary.active_vertex_keys)
    )
    assert auxiliary.audit["gradient_commuting_max_relative_error"] <= (
        _COMMUTING_TOLERANCE
    )
    assert auxiliary.audit[
        "vector_interpolation_commuting_max_relative_error"
    ] <= _COMMUTING_TOLERANCE
    assert auxiliary.audit["curl_gradient_max_abs"] <= _COMMUTING_TOLERANCE

    for parent_index, topology in enumerate((right, left)):
        observed = (
            edge_space._parent_expansions[parent_index]
            @ auxiliary.gradient_matrix
        )
        expected = _local_incidence(topology) @ auxiliary.parent_vertex_expansions[
            parent_index
        ]
        assert _relative_sparse(observed, expected) <= _COMMUTING_TOLERANCE

    repeated = build_lor_hcurl_auxiliary_space(
        [right, left],
        build_lor_slab_edge_space(
            [left, right],
            _empty_floquet(degree),
            phase_x=1.0 + 0.0j,
            phase_y=1.0 + 0.0j,
        ),
    )
    assert repeated.parent_ids == auxiliary.parent_ids
    assert repeated.active_vertex_keys == auxiliary.active_vertex_keys
    for first, second in zip(
        auxiliary.parent_vertex_expansions,
        repeated.parent_vertex_expansions,
        strict=True,
    ):
        assert np.array_equal(first.indptr, second.indptr)
        assert np.array_equal(first.indices, second.indices)
        assert np.array_equal(first.data, second.data)
    for first, second in (
        (auxiliary.gradient_matrix, repeated.gradient_matrix),
        (
            auxiliary.vector_interpolation_matrix,
            repeated.vector_interpolation_matrix,
        ),
    ):
        assert np.array_equal(first.indptr, second.indptr)
        assert np.array_equal(first.indices, second.indices)
        assert np.array_equal(first.data, second.data)


@pytest.mark.parametrize("degree", (2, 3))
def test_vector_h1_line_integrals_and_both_adjoint_identities(degree):
    topology = _topology(degree, 0)
    edge_space = build_lor_slab_edge_space(
        [topology],
        _empty_floquet(degree),
        phase_x=1.0 + 0.0j,
        phase_y=1.0 + 0.0j,
    )
    auxiliary = build_lor_hcurl_auxiliary_space([topology], edge_space)
    coordinates = {
        key: point
        for key, point in zip(topology.vertex_keys, topology.vertices, strict=True)
    }

    constant = np.asarray((1.25, -0.5, 0.75), dtype=np.complex128)
    affine_offset = np.asarray((-0.2, 0.4, 0.1), dtype=np.complex128)
    affine_matrix = np.asarray(
        ((0.3, -0.2, 0.1), (0.4, 0.5, -0.3), (-0.1, 0.2, 0.6)),
        dtype=np.complex128,
    )
    constant_values = np.concatenate(
        [constant for _key in auxiliary.active_vertex_keys]
    )
    affine_values = np.concatenate(
        [
            affine_offset + affine_matrix @ coordinates[key]
            for key in auxiliary.active_vertex_keys
        ]
    )

    for values, field in (
        (constant_values, lambda point: constant),
        (affine_values, lambda point: affine_offset + affine_matrix @ point),
    ):
        observed = auxiliary.apply_vector_h1(values)
        expected = []
        for first, second in edge_space.active_edge_keys:
            expected.append(
                0.5
                * np.dot(
                    coordinates[second] - coordinates[first],
                    field(coordinates[first]) + field(coordinates[second]),
                )
            )
        assert np.allclose(observed, np.asarray(expected), rtol=0.0, atol=1.0e-12)

    scalar_values = np.asarray(
        [complex(index, -2 * index) for index in range(len(auxiliary.active_vertex_keys))]
    )
    assert np.allclose(
        auxiliary.apply_gradient(scalar_values),
        np.asarray(
            [
                scalar_values[auxiliary.active_vertex_keys.index(second)]
                - scalar_values[auxiliary.active_vertex_keys.index(first)]
                for first, second in edge_space.active_edge_keys
            ]
        ),
    )

    rng = np.random.default_rng(2630 + degree)
    edge_values = rng.normal(size=len(edge_space.active_edge_keys)) + 1j * rng.normal(
        size=len(edge_space.active_edge_keys)
    )
    scalar_values = rng.normal(size=len(auxiliary.active_vertex_keys)) + 1j * rng.normal(
        size=len(auxiliary.active_vertex_keys)
    )
    vector_values = rng.normal(
        size=3 * len(auxiliary.active_vertex_keys)
    ) + 1j * rng.normal(size=3 * len(auxiliary.active_vertex_keys))
    for matrix, adjoint, source, target in (
        (
            auxiliary.gradient_matrix,
            auxiliary.apply_gradient_adjoint,
            scalar_values,
            edge_values,
        ),
        (
            auxiliary.vector_interpolation_matrix,
            auxiliary.apply_vector_h1_adjoint,
            vector_values,
            edge_values,
        ),
    ):
        lhs = np.vdot(matrix @ source, target)
        rhs = np.vdot(source, adjoint(target))
        assert (
            abs(lhs - rhs) / max(abs(lhs), abs(rhs), np.finfo(float).tiny)
            <= 1.0e-12
        )


@pytest.mark.parametrize("degree", (2, 3))
def test_periodic_vertex_phase_corner_and_readonly_audit(degree):
    topology = _topology(degree, 7)
    phase_x = np.exp(0.23j)
    phase_y = np.exp(-0.41j)
    edge_space = build_lor_slab_edge_space(
        [topology],
        _synthetic_floquet(degree),
        phase_x=phase_x,
        phase_y=phase_y,
    )
    auxiliary = build_lor_hcurl_auxiliary_space([topology], edge_space)
    assert (
        len(edge_space.active_edge_keys)
        + edge_space.audit["periodic_slave_edge_count"]
        == len(edge_space.physical_edge_keys)
    )
    assert (
        auxiliary.audit["active_vertex_count"]
        + auxiliary.audit["periodic_slave_vertex_count"]
        == auxiliary.audit["physical_vertex_count"]
    )
    assert len(set(auxiliary.active_vertex_keys)) == len(auxiliary.active_vertex_keys)
    assert auxiliary.audit["periodic_slave_vertex_count"] > 0
    assert auxiliary.audit["gradient_commuting_max_relative_error"] <= (
        _COMMUTING_TOLERANCE
    )
    assert auxiliary.audit[
        "vector_interpolation_commuting_max_relative_error"
    ] <= _COMMUTING_TOLERANCE

    vertex_rows = {
        tuple(np.rint(point).astype(int)): row
        for row, point in enumerate(topology.vertices)
        if np.all(np.isclose(point, np.rint(point), rtol=0.0, atol=1.0e-12))
    }
    vertex_expansion = auxiliary.parent_vertex_expansions[0]
    for point, expected_phase in (
        ((1, 0, 0), phase_x),
        ((0, 1, 0), phase_y),
        ((1, 1, 0), phase_x * phase_y),
    ):
        row = vertex_rows[point]
        column, coefficient = _row_entry(vertex_expansion, row)
        assert np.isclose(
            coefficient,
            expected_phase,
            rtol=0.0,
            atol=_COMMUTING_TOLERANCE,
        )
        assert auxiliary.active_vertex_keys[column] != topology.vertex_keys[row]

    for matrix in (
        auxiliary.gradient_matrix,
        auxiliary.vector_interpolation_matrix,
        *auxiliary.parent_vertex_expansions,
    ):
        assert matrix.format == "csr"
        assert not matrix.data.flags.writeable
        assert not matrix.indices.flags.writeable
        assert not matrix.indptr.flags.writeable
    assert auxiliary.audit["factor_count"] == 0
    assert auxiliary.audit["global_dense_object_retained"] is False
    assert auxiliary.audit["global_dense_T_retained"] is False
    assert "schema_version" not in auxiliary.audit
