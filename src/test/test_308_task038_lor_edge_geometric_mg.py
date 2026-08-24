"""Focused S4-A1 local LOR edge-geometric transfer tests."""

from __future__ import annotations

import numpy as np
import pytest

from src.solvers.fullspace_lor_edge_geometric_mg import (
    ADJOINT_LIMIT,
    CHEBYSHEV_DEGREE,
    DE_RHAM_LIMIT,
    LAMBDA_HI_FACTOR,
    LAMBDA_LO_FACTOR,
    LINEARITY_LIMIT,
    METHOD,
    POWER_STEPS,
    POST_POLYNOMIAL_COUNT,
    PRE_POLYNOMIAL_COUNT,
    REPEAT_LIMIT,
    VCYCLE_COUNT,
    FixedChebyshevJacobi,
    build_local_lor_edge_geometric_transfer,
)


@pytest.mark.parametrize("degree", [2, 3])
def test_local_q_edge_is_fixed_four_edge_histopolation(degree: int) -> None:
    transfer = build_local_lor_edge_geometric_transfer(degree)
    q = transfer.edge_transfer
    nonzero = np.abs(q) > 1.0e-13
    row_counts = np.count_nonzero(nonzero, axis=1)
    assert np.max(row_counts) <= 4
    assert np.max(row_counts) == 4
    assert np.any(np.abs(q - np.rint(q)) > 1.0e-10)
    assert transfer.off_stencil_defect <= DE_RHAM_LIMIT
    assert transfer.audit["simple_injection"] is False
    assert transfer.audit["line_integral_histopolation"] is True
    assert transfer.audit["orientation_phase_scope"] == (
        "not_exercised_by_local_A1"
    )
    assert transfer.audit["global_orientation_phase_once"] is None


@pytest.mark.parametrize("degree", [2, 3])
def test_independent_edge_and_curl_oracles_and_derham(degree: int) -> None:
    transfer = build_local_lor_edge_geometric_transfer(degree)
    assert transfer.audit["edge_line_integral_oracle_relative"] <= DE_RHAM_LIMIT
    assert transfer.audit["gradient_commuting_relative"] <= DE_RHAM_LIMIT
    assert transfer.audit["curl_commuting_relative"] <= DE_RHAM_LIMIT
    assert np.all(np.isfinite(transfer.direct_edge_integral))
    assert np.all(np.isfinite(transfer.direct_curl_flux))
    assert transfer.edge_transfer.shape == transfer.direct_edge_integral.shape


@pytest.mark.parametrize("degree", [2, 3])
def test_local_adjoint_linearity_repeat_and_input_unchanged(degree: int) -> None:
    transfer = build_local_lor_edge_geometric_transfer(degree)
    rng = np.random.default_rng(308 + degree)
    coarse = rng.normal(size=12) + 1j * rng.normal(size=12)
    second = rng.normal(size=12) + 1j * rng.normal(size=12)
    fine = rng.normal(size=transfer.edge_transfer.shape[0]) + 1j * rng.normal(
        size=transfer.edge_transfer.shape[0]
    )
    before = coarse.copy()
    alpha = 0.37 + 0.19j
    beta = -0.23 + 0.41j
    observed = transfer.edge_transfer @ (alpha * coarse + beta * second)
    expected = alpha * (transfer.edge_transfer @ coarse) + beta * (
        transfer.edge_transfer @ second
    )
    assert np.linalg.norm(observed - expected) / np.linalg.norm(expected) <= LINEARITY_LIMIT
    lhs = np.vdot(transfer.edge_transfer @ coarse, fine)
    rhs = np.vdot(coarse, transfer.edge_transfer.conj().T @ fine)
    assert abs(lhs - rhs) / max(abs(rhs), np.finfo(float).tiny) <= ADJOINT_LIMIT
    repeated = transfer.edge_transfer @ coarse
    assert np.linalg.norm(repeated - transfer.edge_transfer @ coarse) / max(
        np.linalg.norm(repeated), np.finfo(float).tiny
    ) <= REPEAT_LIMIT
    np.testing.assert_array_equal(coarse, before)
    assert np.all(np.isfinite(repeated))


def test_frozen_s4_a1_surface_has_no_scan_options() -> None:
    assert METHOD == "lor_edge_geometric_mg_v1"
    assert CHEBYSHEV_DEGREE == 3
    assert POWER_STEPS == 10
    assert LAMBDA_HI_FACTOR == 1.10
    assert LAMBDA_LO_FACTOR == 0.10
    assert PRE_POLYNOMIAL_COUNT == 1
    assert POST_POLYNOMIAL_COUNT == 1
    assert VCYCLE_COUNT == 1
    assert "degree" not in FixedChebyshevJacobi.__init__.__code__.co_varnames[1:]


def test_fixed_chebyshev_jacobi_is_deterministic_linear_and_reduces_residual() -> None:
    matrix = np.asarray(
        [[2.0 + 0.0j, 0.25 - 0.1j], [0.25 + 0.1j, 1.5 + 0.0j]],
        dtype=np.complex128,
    )
    smoother = FixedChebyshevJacobi(matrix)
    rhs = np.asarray([1.0 + 0.5j, -0.75 + 0.25j], dtype=np.complex128)
    before = np.linalg.norm(rhs)
    result = smoother.apply(rhs)
    repeated = smoother.apply(rhs)
    residual = rhs - matrix @ result
    assert len(smoother.power_history) == POWER_STEPS
    assert smoother.lambda_hi == LAMBDA_HI_FACTOR * smoother.lambda_power10
    assert smoother.lambda_lo == LAMBDA_LO_FACTOR * smoother.lambda_hi
    assert np.all(np.isfinite(result))
    assert np.linalg.norm(residual) < before
    assert np.linalg.norm(repeated - result) / np.linalg.norm(result) <= REPEAT_LIMIT
    alpha = 0.37 + 0.19j
    beta = -0.23 + 0.41j
    other = np.asarray([-0.4 + 0.75j, 0.6 - 0.2j], dtype=np.complex128)
    other_result = smoother.apply(other)
    combined = smoother.apply(alpha * rhs + beta * other)
    expected = alpha * result + beta * other_result
    assert np.linalg.norm(combined - expected) / np.linalg.norm(expected) <= LINEARITY_LIMIT


def test_fixed_chebyshev_matches_independent_degree_three_polynomial() -> None:
    matrix = np.asarray(
        [[2.0 + 0.0j, 0.25 - 0.1j], [0.25 + 0.1j, 1.5 + 0.0j]],
        dtype=np.complex128,
    )
    smoother = FixedChebyshevJacobi(matrix)
    rhs = np.asarray([1.0 + 0.5j, -0.75 + 0.25j], dtype=np.complex128)
    scaled_rhs = smoother.scale * rhs
    center = 0.5 * (smoother.lambda_hi + smoother.lambda_lo)
    half_width = 0.5 * (smoother.lambda_hi - smoother.lambda_lo)
    scaled_matrix = smoother.scaled_matrix
    identity = np.eye(matrix.shape[0], dtype=np.complex128)
    chebyshev_argument = (center * identity - scaled_matrix) / half_width
    t0 = identity
    t1 = chebyshev_argument
    t2 = 2.0 * chebyshev_argument @ t1 - t0
    t3 = 2.0 * chebyshev_argument @ t2 - t1
    scalar_argument = center / half_width
    scalar_t3 = 4.0 * scalar_argument**3 - 3.0 * scalar_argument
    residual_polynomial = t3 / scalar_t3
    reference_scaled = np.linalg.solve(
        scaled_matrix, (identity - residual_polynomial) @ scaled_rhs
    )
    reference = smoother.scale * reference_scaled
    observed = smoother.apply(rhs)
    assert np.linalg.norm(observed - reference) / np.linalg.norm(reference) <= 1.0e-13


def test_p6_local_transfer_shape_and_authority() -> None:
    transfer = build_local_lor_edge_geometric_transfer(6)
    assert transfer.edge_transfer.shape == (882, 12)
    assert np.max(np.count_nonzero(np.abs(transfer.edge_transfer) > 1.0e-13, axis=1)) <= 4
    assert transfer.audit["edge_line_integral_oracle_relative"] <= DE_RHAM_LIMIT
