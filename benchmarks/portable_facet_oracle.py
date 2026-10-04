"""Independent integer-polynomial/multiprecision integration, never Bessel.

80/110 decimal precision is fixed in the preregistered component design.
Standard-library Decimal power-series integration and an independent fixed
64-point high-precision Gauss rule need no new environment dependency.
"""

from decimal import Decimal, localcontext
from functools import lru_cache
from math import comb, cos, pi

import numpy as np


def coefficients(degree):
    return [
        (-1) ** (degree - j) * comb(degree, j) * comb(degree + j, j)
        for j in range(degree + 1)
    ]


@lru_cache(maxsize=4)
def monomial_integrals(degree, precision):
    with localcontext() as context:
        context.prec = precision + 12
        # Exact integer polynomial integration; this is not a Legendre change
        # of basis and does not use the producer's Fourier/Bessel identity.
        return tuple(
            tuple(
                sum(
                    Decimal(a) / Decimal(n + j + 1)
                    for j, a in enumerate(coefficients(order))
                )
                for order in range(degree + 1)
            )
            for n in range(400)
        )


def exponential(w, precision):
    real, imag = Decimal(0), Decimal(0)
    term = Decimal(1)
    for n in range(400):
        if n % 4 == 0:
            real += term
        elif n % 4 == 1:
            imag += term
        elif n % 4 == 2:
            real -= term
        else:
            imag -= term
        if n > 2 * abs(w) and abs(term) < Decimal(10) ** (-precision - 6):
            return real, imag
        term *= w / Decimal(n + 1)
    raise ValueError("DECIMAL_EXPONENTIAL_BOUND_EXCEEDED")


@lru_cache(maxsize=2)
def gauss64(precision):
    with localcontext() as context:
        context.prec = precision + 12
        points = []
        for i in range(32):
            x = Decimal.from_float(cos(pi * (i + 0.75) / 64.5))
            for _ in range(24):
                p0, p1 = Decimal(1), x
                for degree in range(2, 65):
                    p0, p1 = (
                        p1,
                        ((2 * degree - 1) * x * p1 - (degree - 1) * p0) / degree,
                    )
                derivative = 64 * (x * p1 - p0) / (x * x - 1)
                step = p1 / derivative
                x -= step
                if abs(step) < Decimal(10) ** (-precision - 5):
                    break
            else:
                raise ValueError("DECIMAL_GAUSS_NEWTON_NOT_CONVERGED")
            weight = 1 / ((1 - x * x) * derivative * derivative)
            points.extend([((1 - x) / 2, weight), ((1 + x) / 2, weight)])
        return tuple(points)


def moments(omega, degree, precision, *, direct_quadrature=False):
    if (
        precision not in (80, 110)
        or not 0 <= degree <= 6
        or not np.isfinite(omega)
        or abs(omega) > 56
    ):
        raise ValueError("PREREGISTERED_DECIMAL_ORACLE_SCOPE")
    with localcontext() as context:
        context.prec = precision + 12
        w = Decimal.from_float(float(omega))
        real, imag = [Decimal(0)] * (degree + 1), [Decimal(0)] * (degree + 1)
        if direct_quadrature:
            for t, weight in gauss64(precision):
                er, ei = exponential(w * t, precision)
                for order in range(degree + 1):
                    value = sum(
                        Decimal(a) * t**j for j, a in enumerate(coefficients(order))
                    )
                    real[order] += weight * value * er
                    imag[order] += weight * value * ei
        else:
            integrals = monomial_integrals(degree, precision)
            term = Decimal(1)
            for n in range(400):
                signed = term if n % 4 in (0, 1) else -term
                target = real if n % 2 == 0 else imag
                for order in range(degree + 1):
                    target[order] += signed * integrals[n][order]
                if n > 2 * abs(w) and abs(term) < Decimal(10) ** (-precision - 6):
                    break
                term *= w / Decimal(n + 1)
            else:
                raise ValueError("DECIMAL_INTEGRATION_BOUND_EXCEEDED")
        return np.array(
            [complex(float(r), float(i)) for r, i in zip(real, imag, strict=True)]
        ), [[str(r), str(i)] for r, i in zip(real, imag, strict=True)]


def relative(actual, expected):
    absolute = float(np.linalg.norm(np.asarray(actual) - np.asarray(expected)))
    norm = float(np.linalg.norm(expected))
    denominator = max(norm, 1e-12)
    return dict(
        absolute=absolute,
        reference_norm=norm,
        denominator=denominator,
        near_zero=norm < 1e-12,
        relative=absolute / denominator,
    )


def local_integral(coeff, mx, my, J, k, origin, side):
    # Extended accumulator is separate from oracle integral accuracy. Inputs
    # remain the exact stored binary64 native polynomial; no field is repaired.
    out = np.einsum(
        "a,b,abjc->jc",
        np.asarray(mx, np.clongdouble),
        np.asarray(my, np.clongdouble),
        np.asarray(coeff, np.longdouble),
        optimize=True,
    )
    out *= np.array([J[1, 1], J[0, 0]], np.longdouble)
    pos = np.asarray(origin, np.longdouble).copy()
    if side == "top":
        pos[2] += J[2, 2]
    phase = np.exp(1j * np.sum(np.asarray(k, np.clongdouble) * pos))
    return np.asarray(out * phase, np.complex128)
