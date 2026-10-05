"""Targeted independent checks for Task40's saved W1 moments."""

import mpmath as mp
import numpy as np
import pytest

from src.solvers.task40_w1_moment_reference import (
    legendre_exponential_moments,
    legendre_exponential_moment_table,
    quadrature_legendre_exponential_moments,
    segmented_legendre_exponential_moments,
)


def _direct(k, origin, length, degree, dps):
    ctx = mp.mp.clone()
    ctx.dps = dps
    kw = ctx.mpc(complex(k).real, complex(k).imag)
    x0, span = ctx.mpf(origin), ctx.mpf(length)
    return tuple(
        ctx.quad(
            lambda r, ell=ell: ctx.legendre(ell, 2 * r - 1)
            * ctx.exp(ctx.j * kw * (x0 + span * r)),
            [0, ctx.mpf("0.2"), ctx.mpf("0.4"), ctx.mpf("0.6"), ctx.mpf("0.8"), 1],
        )
        for ell in range(degree + 1)
    )


def test_zero_wavenumber_moments_are_exact():
    values = legendre_exponential_moments(0j, -3.0, 6.25, 6, dps=80)
    assert values[0] == 1
    assert all(value == 0 for value in values[1:])


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_real_signed_high_phase_matches_direct_integral_and_sinc(sign):
    k, x0, length, degree = sign * 8.79645943005142, -6.25, 6.25, 6
    actual = legendre_exponential_moments(k, x0, length, degree, dps=80)
    expected = _direct(k, x0, length, degree, 100)
    ctx = mp.mp.clone()
    ctx.dps = 110
    assert max(abs(a - b) for a, b in zip(actual, expected, strict=True)) < ctx.mpf("1e-70")
    z = ctx.mpf(k) * ctx.mpf(length) / 2
    sinc = ctx.exp(ctx.j * ctx.mpf(k) * (ctx.mpf(x0) + ctx.mpf(length) / 2)) * ctx.sin(z) / z
    assert abs(actual[0] - sinc) < ctx.mpf("1e-70")


@pytest.mark.parametrize("dps", [80, 100])
def test_high_phase_complex_moments_match_direct_integral(dps):
    k = complex(-8.848948219033568, -0.0003133995188219951)
    args = (k, -6.25, 6.25, 6)
    actual = legendre_exponential_moments(*args, dps=dps)
    expected = _direct(*args, dps=dps + 20)
    ctx = mp.mp.clone()
    ctx.dps = dps + 20
    assert max(abs(a - b) for a, b in zip(actual, expected, strict=True)) < ctx.mpf("1e-70")


def test_fixed_100_digit_moment_check_is_stable_against_80_digits():
    args = (complex(-8.848948219033568, 0.0002689381618455788), 8.5, 0.5, 6)
    low = legendre_exponential_moments(*args, dps=80)
    high = legendre_exponential_moments(*args, dps=100)
    ctx = mp.mp.clone()
    ctx.dps = 110
    assert max(abs(a - b) for a, b in zip(low, high, strict=True)) < ctx.mpf("1e-70")


@pytest.mark.parametrize(
    "k,origin,length",
    [
        (complex(-8.545132017764239, 0.0), -6.25, 6.25),  # registered q30 worst y frequency
        (complex(8.97461192517716, 0.0), -6.652173913043478, 8.5 / 46),  # registered maximum x frequency on the saved panel
        (0j, -6.25, 6.25),  # actual n=0 / ky=0 analytic limit
        (complex(-8.848948219033568, -0.0003133995188219951), -6.25, 6.25),
    ],
)
def test_q60_legendre_moments_match_independent_segmented_direct(k, origin, length):
    degree = 6
    q60 = quadrature_legendre_exponential_moments(
        k, origin, length, degree, quadrature_degree=60
    )
    direct = segmented_legendre_exponential_moments(
        k, origin, length, degree, dps=100, segments=5
    )
    analytic = legendre_exponential_moments(k, origin, length, degree, dps=80)
    scipy_table = legendre_exponential_moment_table(
        k, np.asarray([origin]), np.asarray([length]), degree
    )[0]
    direct_np = np.asarray([complex(value) for value in direct], dtype=np.complex128)
    scale = max(float(np.linalg.norm(direct_np)), np.finfo(float).tiny)
    assert np.linalg.norm(np.asarray(q60) - direct_np) / scale <= 1e-10
    assert np.linalg.norm(np.asarray(analytic, dtype=np.complex128) - direct_np) / scale <= 1e-12
    assert np.linalg.norm(scipy_table - direct_np) / scale <= 1e-12


def test_vectorized_analytic_moment_table_matches_scalar_formula():
    origins = np.asarray([-6.25, -6.25 + 6.25, -6.25 + 12.5])
    lengths = np.asarray([6.25, 6.25, 6.25])
    for k in (complex(-8.545132017764239, 0.0), complex(0.0, 0.04), 0j):
        table = legendre_exponential_moment_table(k, origins, lengths, 6)
        expected = np.asarray([
            [complex(value) for value in legendre_exponential_moments(k, x, L, 6)]
            for x, L in zip(origins, lengths, strict=True)
        ])
        np.testing.assert_allclose(table, expected, rtol=3e-13, atol=3e-13)
