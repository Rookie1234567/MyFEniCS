"""Opt-in [0,1] moments and a minimal existing FacetPolynomial consumer.

No material, mode inventory, MPC/owner map or boundary solver is owned here.
The polynomial's physical orientation is already applied by its caller.
"""

import hashlib

import numpy as np

from src.solvers.analytic_face_ports import fourier_legendre


def unit_interval_moments(omega, degree):
    """Integral of P_l(2t-1) exp(i omega t), retaining center and half scale."""
    value = np.asarray(omega)
    if (
        value.dtype.kind not in "fiu"
        or not np.isfinite(value).all()
        or type(degree) is not int
        or not 0 <= degree <= 12
    ):
        raise ValueError("UNIT_INTERVAL_REAL_FINITE_FREQUENCY_AND_DEGREE")
    value = value.astype(np.float64)
    return 0.5 * np.exp(0.5j * value)[..., None] * fourier_legendre(0.5 * value, degree)


def _hash_array(value):
    value = np.ascontiguousarray(value)
    h = hashlib.sha256(str(value.dtype).encode() + str(value.shape).encode())
    h.update(value.tobytes())
    return h.hexdigest()


def facet_identity(polynomial, side, k, J, origin):
    """Exact bytes expected by this local call, including physical wavevector."""
    if side not in ("top", "bottom"):
        raise ValueError("FACET_SIDE_REQUIRED")
    return dict(
        schema="interval_facet.identity.v1",
        side=side,
        degree=polynomial.p,
        coefficients=_hash_array(polynomial.coefficients[side]),
        k=_hash_array(np.asarray(k, np.complex128)),
        J=_hash_array(np.asarray(J, np.float64)),
        origin=_hash_array(np.asarray(origin, np.float64)),
    )


def integrate_receiver_facet(
    polynomial, side, k, J, origin, *, expected, moment_provider=unit_interval_moments
):
    """Replace only the two 1D integrals; keep the receiver's contraction.

    `polynomial` is the receiver's existing FacetPolynomial (or a compatible
    immutable coefficient object). `expected` belongs to the caller's frozen
    input; identity equality never grants a field/solver qualification.
    """
    k = np.asarray(k, np.complex128)
    J = np.asarray(J, np.float64)
    origin = np.asarray(origin, np.float64)
    if (
        k.shape != (3,)
        or J.shape != (3, 3)
        or origin.shape != (3,)
        or not all(np.isfinite(v).all() for v in (k, J, origin))
        or np.any(k[:2].imag != 0)
        or np.any(np.diag(J) <= 0)
        or np.linalg.norm(J - np.diag(np.diag(J))) > 1e-12
    ):
        raise ValueError("AFFINE_AXIS_ALIGNED_REAL_TANGENTIAL_FACET_REQUIRED")
    actual = facet_identity(polynomial, side, k, J, origin)
    if not isinstance(expected, dict) or expected != actual:
        raise ValueError("CALLER_FROZEN_FACET_IDENTITY_MISMATCH")
    p = polynomial.p
    coeff = np.asarray(polynomial.coefficients[side])
    if (
        type(p) is not int
        or not 0 <= p <= 12
        or coeff.ndim != 4
        or coeff.shape[:2] != (p + 1, p + 1)
        or coeff.shape[-1] != 2
        or not np.isfinite(coeff).all()
    ):
        raise ValueError("RECEIVER_LEGENDRE_COEFFICIENT_LAYOUT_REQUIRED")
    ix = moment_provider(float(k[0].real * J[0, 0]), p)
    iy = moment_provider(float(k[1].real * J[1, 1]), p)
    if any(np.shape(v) != (p + 1,) or not np.isfinite(v).all() for v in (ix, iy)):
        raise ValueError("INTERVAL_PROVIDER_RETURN_LAYOUT_REQUIRED")
    # Unchanged receiver polynomial contraction and covariant Piola area.
    local = np.einsum("a,b,abjc->jc", ix, iy, coeff, optimize=True)
    local *= np.array([J[1, 1], J[0, 0]])
    pos = origin.copy()
    if side == "top":
        pos[2] += J[2, 2]
    phase = np.exp(1j * np.dot(k, pos))
    if not np.isfinite(phase) or phase == 0:
        raise ValueError("ORIGIN_PHASE_NOT_REVERSIBLY_REPRESENTABLE")
    local *= phase
    return np.ascontiguousarray(local, np.complex128)


class IntervalFacetAdapter:
    """Small selectable wrapper; the receiver's ordinary default is untouched."""

    def __init__(
        self, polynomial, expected_for_call, *, moment_provider=unit_interval_moments
    ):
        self.polynomial = polynomial
        self.expected_for_call = expected_for_call
        self.moment_provider = moment_provider

    def integral(self, side, k, J, origin, q):
        # q remains part of the compatibility signature; the chosen provider
        # is fixed explicitly. It is never silently reinterpreted as q60.
        return integrate_receiver_facet(
            self.polynomial,
            side,
            k,
            J,
            origin,
            expected=self.expected_for_call(side, k, J, origin, q),
            moment_provider=self.moment_provider,
        )
