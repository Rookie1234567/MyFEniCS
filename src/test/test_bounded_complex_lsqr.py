"""The undamped recurrence must agree with a direct complex LS witness."""

import numpy as np

from src.solvers.bounded_complex_lsqr import lsqr_steps


def test_complex_nonsymmetric_lsqr_from_zero():
    rng = np.random.default_rng(614)
    A = rng.normal(size=(12, 12)) + 1j * rng.normal(size=(12, 12)) + 7 * np.eye(12)
    b = rng.normal(size=12) + 1j * rng.normal(size=12)
    expected = np.linalg.solve(A, b)
    for iteration, x, _ in lsqr_steps(lambda v: A @ v, lambda v: A.conj().T @ v, b):
        result = x.copy()
        if iteration >= 24:
            break
    np.testing.assert_allclose(result, expected, atol=1e-12, rtol=1e-12)
    assert np.linalg.norm(b - A @ result) / np.linalg.norm(b) < 1e-12


def test_zero_rhs_has_no_operator_action():
    def forbidden(_):
        raise AssertionError("zero RHS has no action")

    records = list(lsqr_steps(forbidden, forbidden, np.zeros(5)))
    assert len(records) == 1 and records[0][0] == 0
    assert not np.any(records[0][1])
