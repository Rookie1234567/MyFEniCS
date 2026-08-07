from __future__ import annotations

import numpy as np
import pytest

from src.solvers.static_lor_hcurl_vcycle import build_lor_hcurl_vcycle
from src.solvers.static_lor_h1_vcycle import build_lor_h1_vcycle
from src.test.test_266_task037_extra_lor_h1_hierarchy import _build


_TOLERANCE = 1.0e-12


def _relative(first: np.ndarray, second: np.ndarray) -> float:
    return float(
        np.linalg.norm(first - second)
        / max(float(np.linalg.norm(second)), np.finfo(float).tiny)
    )


def _reference_one(
    hx,
    h1_vcycle,
    rhs: np.ndarray,
    check_scalar_gauge: bool,
) -> np.ndarray:
    matrix = hx.matrix
    auxiliary = hx.auxiliary
    edge_inverse = hx.edge_inverse_diagonal
    solution = 0.5 * edge_inverse * rhs

    residual = rhs - matrix @ solution
    scalar_rhs = auxiliary.apply_gradient_adjoint(residual)
    if check_scalar_gauge:
        assert abs(np.sum(scalar_rhs)) <= _TOLERANCE * max(
            float(np.linalg.norm(scalar_rhs)), 1.0
        )
    solution += auxiliary.apply_gradient(h1_vcycle.apply_scalar(scalar_rhs))

    residual = rhs - matrix @ solution
    vector_rhs = auxiliary.apply_vector_h1_adjoint(residual)
    solution += auxiliary.apply_vector_h1(h1_vcycle.apply_vector(vector_rhs))

    residual = rhs - matrix @ solution
    solution += 0.5 * edge_inverse * residual
    return solution


@pytest.mark.parametrize("periodic", (False, True))
def test_fixed_one_and_two_lor_hcurl_cycles(periodic):
    hierarchy, hx = _build(periodic)
    h1_vcycle = build_lor_h1_vcycle(hierarchy)
    vcycle = build_lor_hcurl_vcycle(hx, h1_vcycle)
    repeated = build_lor_hcurl_vcycle(hx, build_lor_h1_vcycle(hierarchy))
    edge_rows = hx.matrix.shape[0]
    rng = np.random.default_rng(2680 + int(periodic))
    rhs = rng.normal(size=edge_rows) + 1j * rng.normal(size=edge_rows)
    other = rng.normal(size=edge_rows) + 1j * rng.normal(size=edge_rows)

    expected_one = _reference_one(hx, h1_vcycle, rhs, not periodic)
    second_rhs = rhs - hx.matrix @ expected_one
    expected_two = expected_one + _reference_one(
        hx,
        h1_vcycle,
        second_rhs,
        not periodic,
    )
    one = vcycle.apply_one(rhs)
    two = vcycle.apply_two(rhs)
    assert _relative(one, expected_one) <= _TOLERANCE
    assert _relative(two, expected_two) <= _TOLERANCE
    assert np.array_equal(one, vcycle.apply_one(rhs))
    assert np.array_equal(two, vcycle.apply_two(rhs))
    assert np.array_equal(one, repeated.apply_one(rhs))
    assert np.array_equal(two, repeated.apply_two(rhs))

    alpha = 0.31 - 0.17j
    beta = -0.23 + 0.29j
    assert _relative(
        vcycle.apply_one(alpha * rhs + beta * other),
        alpha * one + beta * vcycle.apply_one(other),
    ) <= _TOLERANCE
    assert _relative(
        vcycle.apply_two(alpha * rhs + beta * other),
        alpha * two + beta * vcycle.apply_two(other),
    ) <= _TOLERANCE

    audit = vcycle.audit
    assert vcycle.matrix is hx.matrix
    assert vcycle.auxiliary is hx.auxiliary
    assert vcycle.edge_inverse_diagonal is hx.edge_inverse_diagonal
    assert vcycle.h1_vcycle is h1_vcycle
    assert all(value is not hx for value in vars(vcycle).values())
    assert audit["factor_count"] == 2
    assert audit["coarsest_factor_count"] == 2
    assert audit["fine_intermediate_factor_count"] == 0
    assert audit["fine_p6_trace_factor_count"] == 0
    assert audit["fine_p6_full_factor_count"] == 0
    assert audit["large_lor_factor_count"] == 0
    assert audit["coarsest_only"] is True
    assert audit["scalar_factor_inventory"] == (
        h1_vcycle.audit["scalar_factor_inventory"]
    )
    assert audit["vector_factor_inventory"] == (
        h1_vcycle.audit["vector_factor_inventory"]
    )
    assert audit["restriction_retained"] is False
    assert audit["explicit_action_retained"] is False
    assert audit["global_dense"] is False
    assert audit["literal_p6_galerkin"] is False
    assert audit["retains_fine_hx_object"] is False
    assert audit["unused_aux_jacobi_inverse_retained"] is False
    assert audit["exact_outer_changed"] is False
    assert audit["contraction_not_evaluated"] is True
    assert audit["retained_numeric_payload_lower_bound_bytes"] == sum(
        audit["retained_numeric_payload_components"].values()
    )
    assert audit["retained_numeric_payload_lower_bound_bytes"] > 0
    assert np.isfinite(
        np.linalg.norm(rhs - hx.matrix @ one) / max(np.linalg.norm(rhs), 1.0e-300)
    )
    assert np.isfinite(
        np.linalg.norm(rhs - hx.matrix @ two) / max(np.linalg.norm(rhs), 1.0e-300)
    )


def test_lor_hcurl_vcycle_rejects_wrong_edge_length():
    hierarchy, hx = _build(False)
    vcycle = build_lor_hcurl_vcycle(hx, build_lor_h1_vcycle(hierarchy))
    with pytest.raises(ValueError):
        vcycle.apply_one(np.zeros(hx.matrix.shape[0] + 1))


def test_lor_hcurl_vcycle_requires_hx_h1_operator_identity():
    _hierarchy, hx = _build(False)
    other_hierarchy, _other_hx = _build(False)
    other_h1_vcycle = build_lor_h1_vcycle(other_hierarchy)
    with pytest.raises(ValueError):
        build_lor_hcurl_vcycle(hx, other_h1_vcycle)
