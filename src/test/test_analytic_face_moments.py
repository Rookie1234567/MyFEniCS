import numpy as np
import pytest
from numpy.polynomial.legendre import leggauss, legvander
from src.solvers.analytic_face_ports import (
    fourier_legendre,
    oracle_rule,
    AffineFacePolynomial,
)


@pytest.mark.parametrize("p", [3, 4, 6])
def test_independent_oscillatory_integral_zero_signed_small_large(p):
    z = np.array([0, 1e-14, -1e-8, 0.02, -0.6, 2, -4, 12, -24, 60.0])
    x, w = leggauss(160)
    # No Bessel or producer coefficient transform in this oracle.
    ref = (np.exp(1j * z[:, None] * x) * w) @ legvander(x, p)
    actual = fourier_legendre(z, p)
    assert np.max(abs(ref - actual)) < 3e-13
    assert np.array_equal(actual[0], np.r_[2 + 0j, np.zeros(p)])


def test_a_priori_oracle_is_fixed_and_bounded():
    assert oracle_rule(4, 6) == (24, 32)
    assert oracle_rule(30, 6) == (74, 82)
    with pytest.raises(ValueError):
        oracle_rule(100, 6)


def test_nonphysical_frequency_and_irreversible_origin_phase_rejected():
    p = AffineFacePolynomial(
        np.zeros((4, 4, 2, 3), complex),
        np.array([0.0, 0.0, 1.0]),
        np.array([[0.5, 0, 0], [0, 0.5, 0]]),
        1.0,
        np.array([0, 1]),
        3,
        0,
    )
    with pytest.raises(ValueError, match="COMPLEX_TANGENTIAL"):
        p.integrate(np.array([[1j, 0, 0]]), np.zeros(3))
    with pytest.raises(ValueError, match="REVERSIBLY"):
        p.integrate(np.array([[0, 0, 1000j]]), np.zeros(3))
