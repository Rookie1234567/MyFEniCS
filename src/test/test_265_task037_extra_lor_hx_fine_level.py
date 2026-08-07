from __future__ import annotations

import numpy as np
import pytest

from src.solvers.static_lor_hcurl_auxiliary import (
    build_lor_hcurl_auxiliary_space,
)
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


def _build(degree: int, periodic: bool):
    topology = _topology(degree, 7)
    floquet = _synthetic_floquet(degree) if periodic else _empty_floquet(degree)
    edge_space = build_lor_slab_edge_space(
        [topology],
        floquet,
        phase_x=np.exp(0.23j),
        phase_y=np.exp(-0.41j),
    )
    proxy = build_shifted_lor_proxy([topology], edge_space, _spec())
    auxiliary = build_lor_hcurl_auxiliary_space([topology], edge_space)
    return build_lor_hcurl_hx(proxy, auxiliary), proxy, auxiliary


def _jacobi(matrix, rhs: np.ndarray, steps: int) -> np.ndarray:
    diagonal = np.asarray(matrix.diagonal(), dtype=np.complex128)
    correction = np.zeros_like(rhs, dtype=np.complex128)
    for _ in range(steps):
        correction += 0.5 * (rhs - matrix @ correction) / diagonal
    return correction


def _reference_action(proxy, auxiliary, rhs: np.ndarray):
    matrix = proxy.matrix
    gradient = auxiliary.gradient_matrix
    vector_interpolation = auxiliary.vector_interpolation_matrix
    gradient_adjoint = gradient.conjugate().transpose()
    vector_interpolation_adjoint = vector_interpolation.conjugate().transpose()
    scalar_operator = (gradient_adjoint @ matrix @ gradient).tocsr()
    vector_operator = (
        vector_interpolation_adjoint @ matrix @ vector_interpolation
    ).tocsr()
    for operator in (scalar_operator, vector_operator):
        operator.sum_duplicates()
        operator.sort_indices()
        operator.eliminate_zeros()
    solution = np.zeros_like(rhs, dtype=np.complex128)
    edge_diagonal = np.asarray(matrix.diagonal(), dtype=np.complex128)
    pre = 0.5 * rhs / edge_diagonal
    solution += pre

    residual = rhs - matrix @ solution
    scalar = gradient @ _jacobi(
        scalar_operator,
        gradient_adjoint @ residual,
        2,
    )
    solution += scalar

    residual = rhs - matrix @ solution
    vector = vector_interpolation @ _jacobi(
        vector_operator,
        vector_interpolation_adjoint @ residual,
        2,
    )
    solution += vector

    residual = rhs - matrix @ solution
    post = 0.5 * residual / edge_diagonal
    solution += post
    return solution, scalar, vector, post


def _relative(first: np.ndarray, second: np.ndarray) -> float:
    return float(
        np.linalg.norm(first - second)
        / max(float(np.linalg.norm(second)), np.finfo(float).tiny)
    )


@pytest.mark.parametrize("degree", (2, 3))
@pytest.mark.parametrize("periodic", (False, True))
def test_fixed_finest_level_hx_matches_independent_five_stage_action(
    degree: int,
    periodic: bool,
):
    hx, proxy, auxiliary = _build(degree, periodic)
    rng = np.random.default_rng(2650 + degree + int(periodic))
    edge_count = hx.audit["edge_rows"]
    x = rng.normal(size=edge_count) + 1j * rng.normal(size=edge_count)
    y = rng.normal(size=edge_count) + 1j * rng.normal(size=edge_count)
    rhs = rng.normal(size=edge_count) + 1j * rng.normal(size=edge_count)

    expected, scalar, vector, post = _reference_action(proxy, auxiliary, rhs)
    first = hx.apply(rhs)
    second = hx.apply(rhs)
    assert _relative(first, expected) <= _TOLERANCE
    assert np.array_equal(first, second)
    assert np.linalg.norm(scalar) > 1.0e-14
    assert np.linalg.norm(vector) > 1.0e-14
    assert np.linalg.norm(post) > 1.0e-14
    alpha = 0.31 - 0.22j
    beta = -0.47 + 0.13j
    assert _relative(
        hx.apply(alpha * x + beta * y),
        alpha * hx.apply(x) + beta * hx.apply(y),
    ) <= _TOLERANCE

    gradient = auxiliary.gradient_matrix
    vector_interpolation = auxiliary.vector_interpolation_matrix
    expected_scalar = (
        gradient.conjugate().transpose() @ proxy.matrix @ gradient
    ).tocsr()
    expected_vector = (
        vector_interpolation.conjugate().transpose()
        @ proxy.matrix
        @ vector_interpolation
    ).tocsr()
    for expected_operator in (expected_scalar, expected_vector):
        expected_operator.sum_duplicates()
        expected_operator.sort_indices()
        expected_operator.eliminate_zeros()
    assert np.array_equal(hx.scalar_operator.indptr, expected_scalar.indptr)
    assert np.array_equal(hx.scalar_operator.indices, expected_scalar.indices)
    assert _relative(hx.scalar_operator.data, expected_scalar.data) <= _TOLERANCE
    assert np.array_equal(hx.vector_operator.indptr, expected_vector.indptr)
    assert np.array_equal(hx.vector_operator.indices, expected_vector.indices)
    assert _relative(hx.vector_operator.data, expected_vector.data) <= _TOLERANCE
    assert hx.audit["factor_count"] == 0
    assert hx.audit["large_factor"] is False
    assert hx.audit["global_dense"] is False
    assert hx.audit["literal_p6_galerkin"] is False
    assert hx.audit["shifted_proxy"] is True
    assert hx.audit["omega"] == 0.5
    assert hx.audit["edge_pre_steps"] == 1
    assert hx.audit["scalar_steps"] == 2
    assert hx.audit["vector_steps"] == 2
    assert hx.audit["edge_post_steps"] == 1
    assert hx.audit["inverse_diagonal_bytes"] > 0


@pytest.mark.parametrize("degree", (2, 3))
def test_hx_operators_and_storage_are_readonly_and_length_is_checked(degree):
    hx, proxy, _auxiliary = _build(degree, periodic=False)
    for matrix in (hx.matrix, hx.scalar_operator, hx.vector_operator):
        assert matrix.data.flags.writeable is False
        assert matrix.indices.flags.writeable is False
        assert matrix.indptr.flags.writeable is False
    for name in (
        "_edge_inverse_diagonal",
        "_scalar_inverse_diagonal",
        "_vector_inverse_diagonal",
    ):
        assert getattr(hx, name).flags.writeable is False
    assert hx.matrix is proxy.matrix
    assert "_a_adjoint" not in vars(hx)
    with pytest.raises(ValueError):
        hx.apply(np.zeros(proxy.matrix.shape[0] + 1, dtype=np.complex128))
