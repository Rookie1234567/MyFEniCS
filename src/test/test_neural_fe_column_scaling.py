import numpy as np
import pytest
from scipy import sparse

from src.solvers.neural_fe_column_scaling import (
    ColumnScaledOperator,
    ScalingDefinitionError,
    column_norm_scaling,
)


def test_duplicate_and_phase_contributions_are_merged_before_norm():
    matrix = sparse.coo_matrix(
        ([1 + 2j, 2 - 2j, 4j, 3j], ([0, 0, 1, 0], [0, 0, 0, 1])), shape=(2, 2)
    )
    c, D = column_norm_scaling(matrix)
    np.testing.assert_allclose(c, [5, 3], rtol=1e-15)
    np.testing.assert_allclose(D, 1 / c, rtol=0, atol=0)


@pytest.mark.parametrize("value", [0, complex(float("nan")), float("inf"), 1e-320])
def test_undefined_scaling_is_not_silently_replaced(value):
    with pytest.raises(ScalingDefinitionError):
        column_norm_scaling(sparse.csr_matrix([[value]]))


def test_extreme_representable_column_uses_stable_norm():
    c, D = column_norm_scaling(sparse.csr_matrix([[1e200], [1e200]]))
    assert np.isfinite(c).all() and np.isfinite(D).all()
    np.testing.assert_allclose(c, [np.sqrt(2) * 1e200], rtol=1e-15)


def test_complex_nonhermitian_forward_adjoint_and_recovered_coordinates():
    rng = np.random.default_rng(7)
    A = rng.normal(size=(6, 6)) + 1j * rng.normal(size=(6, 6))
    A *= np.array([1e-4, 2.0, 3e3, 0.2, 9.0, 0.1])[None, :]

    class Action:
        size = 6

        def apply(self, x, *, adjoint=False):
            return (A.conj().T if adjoint else A) @ x

    _, D = column_norm_scaling(sparse.csr_matrix(A))
    scaled = ColumnScaledOperator(Action(), D)
    y = rng.normal(size=6) + 1j * rng.normal(size=6)
    v = rng.normal(size=6) + 1j * rng.normal(size=6)
    np.testing.assert_allclose(scaled.apply(y), A @ (D * y), rtol=1e-15)
    np.testing.assert_allclose(
        scaled.adjoint(v), D.conj() * (A.conj().T @ v), rtol=1e-15
    )
    np.testing.assert_allclose(
        np.vdot(v, scaled.apply(y)), np.vdot(scaled.adjoint(v), y), rtol=1e-14
    )
    assert abs(np.vdot(v, scaled.apply(y)) - np.vdot(A.conj().T @ v, y)) > 1e-3


def test_diagonal_wrapper_preserves_original_lsqr_recurrence_and_zero_start():
    from src.solvers.bounded_complex_lsqr import lsqr_steps

    A = np.array([[1j, 0, 0], [0, 3 - 2j, 0], [0, 0, 2e4j]])
    exact = np.array([0.3 + 0.5j, 1 - 0.2j, 2 + 0.7j])
    rhs = A @ exact

    class Action:
        size = 3

        def apply(self, x, *, adjoint=False):
            return (A.conj().T if adjoint else A) @ x

    _, D = column_norm_scaling(sparse.csr_matrix(A))
    scaled = ColumnScaledOperator(Action(), D)
    _, y, _ = next(lsqr_steps(scaled.apply, scaled.adjoint, rhs))
    np.testing.assert_allclose(scaled.recover(y), exact, rtol=1e-14, atol=1e-14)
