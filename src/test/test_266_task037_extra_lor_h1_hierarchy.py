from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp

from src.solvers.static_lor_hcurl_auxiliary import (
    build_lor_hcurl_auxiliary_space,
)
from src.solvers.static_lor_h1_hierarchy import build_lor_h1_hierarchy
from src.solvers.static_lor_hcurl_hx import build_lor_hcurl_hx
from src.solvers.static_lor_hcurl_proxy import build_shifted_lor_proxy
from src.solvers.static_lor_hcurl_transfer import build_lor_slab_edge_space
from src.test.test_259_task037_extra_lor_slab_edges import (
    _empty_floquet,
    _synthetic_floquet,
    _topology,
)
from src.test.test_264_task037_extra_lor_shifted_proxy import _spec


_TOLERANCE = 1.0e-12


def _build(periodic: bool):
    topologies = [
        _topology(3, 10),
        _topology(3, 2, (1.0, 0.0, 0.0)),
    ]
    floquet = _synthetic_floquet(3) if periodic else _empty_floquet(3)
    edge_space = build_lor_slab_edge_space(
        topologies,
        floquet,
        phase_x=np.exp(0.23j),
        phase_y=np.exp(-0.41j),
    )
    proxy = build_shifted_lor_proxy(topologies, edge_space, _spec())
    auxiliary = build_lor_hcurl_auxiliary_space(topologies, edge_space)
    hx = build_lor_hcurl_hx(proxy, auxiliary)
    hierarchy = build_lor_h1_hierarchy(
        hx.scalar_operator,
        hx.vector_operator,
    )
    return hierarchy, hx


def _assert_same_csr(first: sp.csr_matrix, second: sp.csr_matrix) -> None:
    assert np.array_equal(first.indptr, second.indptr)
    assert np.array_equal(first.indices, second.indices)
    assert np.array_equal(first.data, second.data)


def _relative_inner(first: complex, second: complex) -> float:
    return float(abs(first - second) / max(abs(second), np.finfo(float).tiny))


def _independent_aggregates(matrix: sp.csr_matrix):
    aggregate_of = np.full(matrix.shape[0], -1, dtype=np.int64)
    aggregate_count = 0
    for row in range(matrix.shape[0]):
        if aggregate_of[row] >= 0:
            continue
        start = int(matrix.indptr[row])
        end = int(matrix.indptr[row + 1])
        best_column = -1
        best_weight = -1.0
        for position in range(start, end):
            column = int(matrix.indices[position])
            weight = float(abs(matrix.data[position]))
            if column == row or aggregate_of[column] >= 0 or weight <= 0.0:
                continue
            if weight > best_weight or (
                weight == best_weight
                and (best_column < 0 or column < best_column)
            ):
                best_column = column
                best_weight = weight
        aggregate_of[row] = aggregate_count
        if best_column >= 0:
            aggregate_of[best_column] = aggregate_count
        aggregate_count += 1
    return aggregate_of, aggregate_count


def _independent_smoothed_prolongation(
    operator: sp.csr_matrix,
    aggregate_of: np.ndarray,
    aggregate_count: int,
    component_count: int,
) -> sp.csr_matrix:
    fine_rows = component_count * aggregate_of.size
    rows = np.arange(fine_rows, dtype=np.int64)
    vertices = rows // component_count
    components = rows % component_count
    columns = component_count * aggregate_of[vertices] + components
    p0 = sp.csr_matrix(
        (
            np.ones(fine_rows, dtype=np.complex128),
            (rows, columns),
        ),
        shape=(fine_rows, component_count * aggregate_count),
        dtype=np.complex128,
    )
    diagonal = np.asarray(operator.diagonal(), dtype=np.complex128)
    scale = max(float(np.max(np.abs(diagonal))), np.finfo(float).tiny)
    threshold = 1.0e-14 * scale
    assert np.all(np.abs(diagonal) > threshold)
    smoothed = (
        p0
        - 0.5 * sp.diags(1.0 / diagonal, format="csr") @ (operator @ p0)
    ).tocsr()
    smoothed.sum_duplicates()
    smoothed.sort_indices()
    smoothed.eliminate_zeros()
    return smoothed


def _assert_sparse_close(first: sp.csr_matrix, second: sp.csr_matrix) -> None:
    assert first.shape == second.shape
    difference = (first - second).tocsr()
    numerator = float(np.linalg.norm(difference.data))
    denominator = max(float(np.linalg.norm(second.data)), np.finfo(float).tiny)
    assert numerator / denominator <= _TOLERANCE


@pytest.mark.parametrize("periodic", (False, True))
def test_paired_h1_hierarchy_is_deterministic_galerkin_and_adjoint(periodic):
    hierarchy, hx = _build(periodic)
    repeated, _ = _build(periodic)
    scalar_rows = [operator.shape[0] for operator in hierarchy.scalar_operators]
    vector_rows = [operator.shape[0] for operator in hierarchy.vector_operators]
    assert scalar_rows[0] > 32
    assert scalar_rows[-1] <= 32
    assert all(
        next_rows < current_rows
        for current_rows, next_rows in zip(scalar_rows, scalar_rows[1:])
    )
    assert vector_rows == [3 * rows for rows in scalar_rows]
    assert len(hierarchy.scalar_prolongations) == len(scalar_rows) - 1
    assert hierarchy.scalar_operators[0] is hx.scalar_operator
    assert hierarchy.vector_operators[0] is hx.vector_operator

    for first, second in zip(
        hierarchy.scalar_operators,
        repeated.scalar_operators,
        strict=True,
    ):
        _assert_same_csr(first, second)
    for first, second in zip(
        hierarchy.vector_operators,
        repeated.vector_operators,
        strict=True,
    ):
        _assert_same_csr(first, second)
    for first, second in zip(
        hierarchy.scalar_prolongations,
        repeated.scalar_prolongations,
        strict=True,
    ):
        _assert_same_csr(first, second)
    for first, second in zip(
        hierarchy.vector_prolongations,
        repeated.vector_prolongations,
        strict=True,
    ):
        _assert_same_csr(first, second)

    rng = np.random.default_rng(2660 + int(periodic))
    for level, scalar_prolongation in enumerate(
        hierarchy.scalar_prolongations
    ):
        vector_prolongation = hierarchy.vector_prolongations[level]
        aggregate_of, aggregate_count = _independent_aggregates(
            hierarchy.scalar_operators[level]
        )
        expected_scalar_prolongation = _independent_smoothed_prolongation(
            hierarchy.scalar_operators[level],
            aggregate_of,
            aggregate_count,
            1,
        )
        expected_vector_prolongation = _independent_smoothed_prolongation(
            hierarchy.vector_operators[level],
            aggregate_of,
            aggregate_count,
            3,
        )
        assert aggregate_count == scalar_prolongation.shape[1]
        _assert_sparse_close(
            expected_scalar_prolongation,
            scalar_prolongation,
        )
        _assert_sparse_close(
            expected_vector_prolongation,
            vector_prolongation,
        )
        assert scalar_prolongation.shape[1] == hierarchy.audit[
            "aggregate_counts"
        ][level]
        assert vector_prolongation.shape[1] == 3 * scalar_prolongation.shape[1]
        expected_scalar = (
            scalar_prolongation.conjugate().transpose()
            @ hierarchy.scalar_operators[level]
            @ scalar_prolongation
        ).tocsr()
        expected_vector = (
            vector_prolongation.conjugate().transpose()
            @ hierarchy.vector_operators[level]
            @ vector_prolongation
        ).tocsr()
        _assert_same_csr(
            expected_scalar,
            hierarchy.scalar_operators[level + 1],
        )
        _assert_same_csr(
            expected_vector,
            hierarchy.vector_operators[level + 1],
        )

        scalar_coarse = rng.normal(size=scalar_prolongation.shape[1]) + 1j * rng.normal(
            size=scalar_prolongation.shape[1]
        )
        scalar_fine = rng.normal(size=scalar_prolongation.shape[0]) + 1j * rng.normal(
            size=scalar_prolongation.shape[0]
        )
        scalar_left = np.vdot(
            hierarchy.apply_scalar_prolongation(level, scalar_coarse),
            scalar_fine,
        )
        scalar_right = np.vdot(
            scalar_coarse,
            hierarchy.apply_scalar_restriction(level, scalar_fine),
        )
        assert _relative_inner(scalar_left, scalar_right) <= _TOLERANCE

        vector_coarse = rng.normal(size=vector_prolongation.shape[1]) + 1j * rng.normal(
            size=vector_prolongation.shape[1]
        )
        vector_fine = rng.normal(size=vector_prolongation.shape[0]) + 1j * rng.normal(
            size=vector_prolongation.shape[0]
        )
        vector_left = np.vdot(
            hierarchy.apply_vector_prolongation(level, vector_coarse),
            vector_fine,
        )
        vector_right = np.vdot(
            vector_coarse,
            hierarchy.apply_vector_restriction(level, vector_fine),
        )
        assert _relative_inner(vector_left, vector_right) <= _TOLERANCE

    if not periodic:
        for prolongation in hierarchy.scalar_prolongations:
            constant = np.ones(prolongation.shape[1], dtype=np.complex128)
            assert np.max(np.abs(prolongation @ constant - 1.0)) <= _TOLERANCE

    for matrix in (
        *hierarchy.scalar_operators,
        *hierarchy.vector_operators,
        *hierarchy.scalar_prolongations,
        *hierarchy.vector_prolongations,
    ):
        assert matrix.data.flags.writeable is False
        assert matrix.indices.flags.writeable is False
        assert matrix.indptr.flags.writeable is False
    assert hierarchy.audit["factor_count"] == 0
    assert hierarchy.audit["restriction_retained"] is False
    assert hierarchy.audit["global_dense"] is False
    assert hierarchy.audit["large_factor"] is False
    assert hierarchy.audit["shared_vertex_aggregates"] is True
    assert hierarchy.audit["component_order"] == "vertex_interleaved_xyz"
    assert hierarchy.audit["retained_csr_payload_bytes"] > 0


def test_pairwise_hierarchy_fails_closed_without_strict_reduction():
    scalar = sp.eye(33, format="csr", dtype=np.complex128)
    vector = sp.eye(99, format="csr", dtype=np.complex128)
    with pytest.raises(RuntimeError, match="did not reduce"):
        build_lor_h1_hierarchy(scalar, vector)
