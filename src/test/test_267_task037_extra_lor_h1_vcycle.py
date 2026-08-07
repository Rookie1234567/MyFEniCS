from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse.linalg as spla

from src.solvers.static_lor_h1_vcycle import build_lor_h1_vcycle
from src.test.test_266_task037_extra_lor_h1_hierarchy import _build


_TOLERANCE = 1.0e-12


def _relative(first: np.ndarray, second: np.ndarray) -> float:
    return float(
        np.linalg.norm(first - second)
        / max(float(np.linalg.norm(second)), np.finfo(float).tiny)
    )


def _reference_vcycle(
    operators,
    prolongations,
    rhs: np.ndarray,
    gauge: bool,
    level: int = 0,
) -> np.ndarray:
    operator = operators[level]
    if level == len(operators) - 1:
        if gauge:
            factor = spla.splu(operator[1:, 1:].tocsc())
            solution = np.zeros_like(rhs, dtype=np.complex128)
            solution[1:] = factor.solve(rhs[1:])
            return solution
        return np.asarray(spla.splu(operator.tocsc()).solve(rhs))
    diagonal = np.asarray(operator.diagonal(), dtype=np.complex128)
    correction = 0.5 * rhs / diagonal
    residual = rhs - operator @ correction
    prolongation = prolongations[level]
    coarse_rhs = prolongation.conjugate().transpose() @ residual
    correction += prolongation @ _reference_vcycle(
        operators,
        prolongations,
        np.asarray(coarse_rhs, dtype=np.complex128),
        gauge,
        level + 1,
    )
    residual = rhs - operator @ correction
    correction += 0.5 * residual / diagonal
    return correction


def _assert_coarse_factor_solves(
    factor,
    operator,
    gauge: bool,
    rng: np.random.Generator,
) -> None:
    if gauge:
        exact = rng.normal(size=operator.shape[0]) + 1j * rng.normal(
            size=operator.shape[0]
        )
        rhs = operator @ exact
        reduced_solution = factor.solve(rhs[1:])
        reduced_residual = operator[1:, 1:] @ reduced_solution - rhs[1:]
        full_solution = np.zeros_like(rhs, dtype=np.complex128)
        full_solution[1:] = reduced_solution
        full_residual = operator @ full_solution - rhs
        assert float(
            np.linalg.norm(full_residual)
            / max(float(np.linalg.norm(rhs)), np.finfo(float).tiny)
        ) <= _TOLERANCE
        assert float(
            np.linalg.norm(reduced_residual)
            / max(float(np.linalg.norm(rhs[1:])), np.finfo(float).tiny)
        ) <= _TOLERANCE
    else:
        rhs = rng.normal(size=operator.shape[0]) + 1j * rng.normal(
            size=operator.shape[0]
        )
        solution = factor.solve(rhs)
        residual = operator @ solution - rhs
        assert float(
            np.linalg.norm(residual)
            / max(float(np.linalg.norm(rhs)), np.finfo(float).tiny)
        ) <= _TOLERANCE


@pytest.mark.parametrize("periodic", (False, True))
def test_fixed_vcycle_matches_independent_recursive_reference(periodic):
    hierarchy, _ = _build(periodic)
    vcycle = build_lor_h1_vcycle(hierarchy)
    repeated = build_lor_h1_vcycle(hierarchy)
    audit = vcycle.audit
    scalar_gauge = bool(audit["scalar_constant_nullspace"])
    assert scalar_gauge is (not periodic)
    coarse_scalar_rows = hierarchy.scalar_operators[-1].shape[0]
    assert audit["scalar_factor_inventory"]["rows"] == (
        coarse_scalar_rows - int(scalar_gauge)
    )
    assert audit["vector_factor_inventory"]["rows"] == (
        hierarchy.vector_operators[-1].shape[0]
    )
    assert audit["factor_count"] == 2
    assert audit["coarsest_factor_count"] == 2
    assert audit["fine_intermediate_factor_count"] == 0
    assert audit["coarsest_only"] is True
    assert audit["large_factor"] is False
    assert audit["global_dense"] is False
    assert audit["restriction_retained"] is False
    assert audit["hierarchy_payload_reference_bytes"] == (
        hierarchy.audit["retained_csr_payload_bytes"]
    )

    rng = np.random.default_rng(2670 + int(periodic))
    scalar_source = rng.normal(
        size=hierarchy.scalar_operators[0].shape[0]
    ) + 1j * rng.normal(size=hierarchy.scalar_operators[0].shape[0])
    vector_source = rng.normal(
        size=hierarchy.vector_operators[0].shape[0]
    ) + 1j * rng.normal(size=hierarchy.vector_operators[0].shape[0])
    scalar_rhs = (
        hierarchy.scalar_operators[0] @ scalar_source
        if not periodic
        else scalar_source
    )
    scalar_expected = _reference_vcycle(
        hierarchy.scalar_operators,
        hierarchy.scalar_prolongations,
        scalar_rhs,
        scalar_gauge,
    )
    vector_expected = _reference_vcycle(
        hierarchy.vector_operators,
        hierarchy.vector_prolongations,
        vector_source,
        False,
    )
    assert _relative(vcycle.apply_scalar(scalar_rhs), scalar_expected) <= _TOLERANCE
    assert _relative(vcycle.apply_vector(vector_source), vector_expected) <= _TOLERANCE
    assert np.array_equal(vcycle.apply_scalar(scalar_rhs), vcycle.apply_scalar(scalar_rhs))
    assert np.array_equal(vcycle.apply_vector(vector_source), vcycle.apply_vector(vector_source))
    assert np.array_equal(vcycle.apply_scalar(scalar_rhs), repeated.apply_scalar(scalar_rhs))
    assert np.array_equal(vcycle.apply_vector(vector_source), repeated.apply_vector(vector_source))

    alpha = 0.27 - 0.19j
    beta = -0.41 + 0.16j
    scalar_other = rng.normal(size=scalar_rhs.size) + 1j * rng.normal(
        size=scalar_rhs.size
    )
    vector_other = rng.normal(size=vector_source.size) + 1j * rng.normal(
        size=vector_source.size
    )
    assert _relative(
        vcycle.apply_scalar(alpha * scalar_rhs + beta * scalar_other),
        alpha * vcycle.apply_scalar(scalar_rhs)
        + beta * vcycle.apply_scalar(scalar_other),
    ) <= _TOLERANCE
    assert _relative(
        vcycle.apply_vector(alpha * vector_source + beta * vector_other),
        alpha * vcycle.apply_vector(vector_source)
        + beta * vcycle.apply_vector(vector_other),
    ) <= _TOLERANCE

    _assert_coarse_factor_solves(
        vcycle._scalar_factor,
        hierarchy.scalar_operators[-1],
        scalar_gauge,
        rng,
    )
    _assert_coarse_factor_solves(
        vcycle._vector_factor,
        hierarchy.vector_operators[-1],
        False,
        rng,
    )
    for inverse in (
        *vcycle._scalar_inverse_diagonals,
        *vcycle._vector_inverse_diagonals,
    ):
        assert inverse.flags.writeable is False
    assert audit["inverse_diagonal_bytes"] > 0
    assert audit["scalar_factor_inventory"]["factor_payload_lower_bound_bytes"] > 0
    assert audit["vector_factor_inventory"]["factor_payload_lower_bound_bytes"] > 0


def test_vcycle_rejects_one_wrong_length_per_component():
    hierarchy, _ = _build(False)
    vcycle = build_lor_h1_vcycle(hierarchy)
    with pytest.raises(ValueError):
        vcycle.apply_scalar(np.zeros(hierarchy.scalar_operators[0].shape[0] + 1))
    with pytest.raises(ValueError):
        vcycle.apply_vector(np.zeros(hierarchy.vector_operators[0].shape[0] + 1))
