"""Small algebraic checks for the bounded W1 local recovery helper."""

import numpy as np
import pytest
import scipy.linalg

from src.solvers.task40_w1_local_probe import solve_local_rhs


def test_local_rhs_solver_reuses_factor_for_vector_and_block_rhs(monkeypatch):
    rng = np.random.default_rng(410)
    matrix = rng.normal(size=(8, 8)) + 1j * rng.normal(size=(8, 8))
    matrix += np.diag(np.linspace(2.0, 4.0, len(matrix)))
    factor = scipy.linalg.lu_factor(matrix)
    exact = rng.normal(size=8) + 1j * rng.normal(size=8)
    rhs = matrix @ exact
    block_exact = np.column_stack((exact, 2.0 * exact - 1j * exact))
    block_rhs = matrix @ block_exact

    def reject_refactor(*_args, **_kwargs):
        raise AssertionError("the local helper must reuse its supplied factor")

    monkeypatch.setattr(scipy.linalg, "lu_factor", reject_refactor)
    solution, facts = solve_local_rhs(
        matrix, factor, rhs, reference_solution=exact
    )
    block_solution, block_facts = solve_local_rhs(
        matrix, factor, block_rhs, max_corrections=3
    )

    np.testing.assert_allclose(solution, exact, rtol=2e-13, atol=2e-13)
    np.testing.assert_allclose(block_solution, block_exact, rtol=2e-13, atol=2e-13)
    for record in (facts, block_facts):
        assert record["factor_reused"] is True
        assert record["refactor_count"] == 0
        assert record["lu_solve_call_count"] == 1 + len(record["correction_attempts"])
        assert record["accepted_corrections"] <= 3
        assert record["final_relative_residual"] <= record["initial_relative_residual"]
        assert len(record["residual_accumulator_receipt"]["dtype"]) > 0


def test_local_rhs_solver_bounds_corrections_and_rejects_nonfinite_inputs():
    matrix = np.asarray([[2.0, 1.0], [0.0, 3.0]], dtype=np.complex128)
    factor = scipy.linalg.lu_factor(matrix)
    rhs = np.asarray([1.0, 2.0], dtype=np.complex128)

    with pytest.raises(ValueError, match="correction budget"):
        solve_local_rhs(matrix, factor, rhs, max_corrections=4)
    with pytest.raises(ValueError, match="finite"):
        solve_local_rhs(matrix, factor, np.asarray([np.inf, 0.0]))


def test_local_rhs_solver_rejects_nonfinite_initial_solution():
    matrix = np.asarray([[1.0, 0.0], [0.0, 0.0]], dtype=np.complex128)
    rhs = np.asarray([1.0, 1.0], dtype=np.complex128)
    with pytest.warns(scipy.linalg.LinAlgWarning):
        factor = scipy.linalg.lu_factor(matrix)
    with pytest.raises(FloatingPointError, match="initial local LU solution"):
        solve_local_rhs(matrix, factor, rhs)
