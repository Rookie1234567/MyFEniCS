"""Independent high-precision Legendre/exponential moments for W1 checks."""
from __future__ import annotations

import math
import mpmath as mp


def legendre_exponential_moments(
    wave_number: complex, origin: float, length: float, degree: int, *, dps: int = 80
) -> tuple[mp.mpc, ...]:
    """Integrate P_l(2r-1) exp(i*k*(origin+length*r)) over r in [0,1].

    Uses exp(i*k*(x0+L/2))*i**l*j_l(k*L/2). Integer-order spherical-Bessel
    parity is applied before the half-integer Bessel formula to avoid its
    principal-square-root branch cut for negative-real arguments.
    """
    if isinstance(degree, bool) or not isinstance(degree, int) or degree < 0:
        raise ValueError("degree must be a nonnegative integer")
    if isinstance(dps, bool) or not isinstance(dps, int) or dps < 30:
        raise ValueError("dps must be an integer of at least 30")
    if not math.isfinite(float(origin)) or not math.isfinite(float(length)):
        raise ValueError("origin and length must be finite")
    if float(length) <= 0:
        raise ValueError("length must be positive")
    value = complex(wave_number)
    if not math.isfinite(value.real) or not math.isfinite(value.imag):
        raise ValueError("wave number must be finite")

    ctx = mp.mp.clone()
    ctx.dps = dps
    k = ctx.mpc(value.real, value.imag)
    x0, span = ctx.mpf(float(origin)), ctx.mpf(float(length))
    z = k * span / 2
    if z == 0:
        return tuple(ctx.mpf(1) if ell == 0 else ctx.mpf(0) for ell in range(degree + 1))
    phase = ctx.exp(ctx.j * k * (x0 + span / 2))
    argument = -z if z.real < 0 else z
    moments = []
    for ell in range(degree + 1):
        spherical_j = ctx.sqrt(ctx.pi / (2 * argument)) * ctx.besselj(
            ell + ctx.mpf("0.5"), argument
        )
        parity = -1 if z.real < 0 and ell % 2 else 1
        moments.append(phase * (ctx.j**ell) * parity * spherical_j)
    return tuple(moments)
