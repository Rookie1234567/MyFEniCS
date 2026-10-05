"""Targeted independent checks for Task40's saved W1 moments."""

import mpmath as mp
import pytest

from src.solvers.task40_w1_moment_reference import legendre_exponential_moments


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
