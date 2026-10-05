"""Independent high-precision Legendre/exponential moments for W1 checks."""
from __future__ import annotations

import math
import mpmath as mp
import numpy as np


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


def segmented_legendre_exponential_moments(
    wave_number: complex,
    origin: float,
    length: float,
    degree: int,
    *,
    dps: int = 100,
    segments: int = 5,
) -> tuple[mp.mpc, ...]:
    """Directly integrate Legendre moments on equal subintervals.

    This is an independent finite witness for the closed-form spherical-Bessel
    moments above.  It deliberately uses segmented adaptive quadrature rather
    than the closed form or a Gauss rule.  The default partition is
    ``[0, .2, .4, .6, .8, 1]``, matching the registered W1 witnesses.
    """
    if isinstance(degree, bool) or not isinstance(degree, int) or degree < 0:
        raise ValueError("degree must be a nonnegative integer")
    if isinstance(dps, bool) or not isinstance(dps, int) or dps < 30:
        raise ValueError("dps must be an integer of at least 30")
    if isinstance(segments, bool) or not isinstance(segments, int) or segments < 1:
        raise ValueError("segments must be a positive integer")
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
    breaks = [ctx.mpf(i) / segments for i in range(segments + 1)]
    return tuple(
        ctx.quad(
            lambda r, ell=ell: ctx.legendre(ell, 2 * r - 1)
            * ctx.exp(ctx.j * k * (x0 + span * r)),
            breaks,
        )
        for ell in range(degree + 1)
    )


def quadrature_legendre_exponential_moments(
    wave_number: complex,
    origin: float,
    length: float,
    degree: int,
    *,
    quadrature_degree: int = 60,
) -> tuple[complex, ...]:
    """Evaluate the finite Gauss rule used by the W1 directional moment path."""
    if isinstance(degree, bool) or not isinstance(degree, int) or degree < 0:
        raise ValueError("degree must be a nonnegative integer")
    if (
        isinstance(quadrature_degree, bool)
        or not isinstance(quadrature_degree, int)
        or quadrature_degree < 1
    ):
        raise ValueError("quadrature_degree must be a positive integer")
    if not math.isfinite(float(origin)) or not math.isfinite(float(length)):
        raise ValueError("origin and length must be finite")
    if float(length) <= 0:
        raise ValueError("length must be positive")
    value = complex(wave_number)
    if not math.isfinite(value.real) or not math.isfinite(value.imag):
        raise ValueError("wave number must be finite")

    import basix

    rule, weights = basix.make_quadrature(
        basix.CellType.interval, quadrature_degree
    )
    r = rule[:, 0]
    values = np.polynomial.legendre.legvander(2 * r - 1, degree)
    phase = np.exp(1j * value * (float(origin) + float(length) * r))
    moments = (weights * phase) @ values
    return tuple(complex(moment) for moment in moments)


def legendre_exponential_moment_table(
    wave_number: complex,
    origins: np.ndarray,
    lengths: np.ndarray,
    degree: int,
) -> np.ndarray:
    """Vectorized closed-form moments for unique frequency/cell axes.

    The result is a double-precision analytic reference table, not a Gauss
    quadrature table. High-precision agreement is checked separately on the
    registered finite witnesses.
    """
    if isinstance(degree, bool) or not isinstance(degree, int) or degree < 0:
        raise ValueError("degree must be a nonnegative integer")
    origins = np.asarray(origins, dtype=np.float64)
    lengths = np.asarray(lengths, dtype=np.float64)
    value = complex(wave_number)
    if (
        origins.ndim != 1
        or lengths.shape != origins.shape
        or not np.isfinite(origins).all()
        or not np.isfinite(lengths).all()
        or np.any(lengths <= 0)
        or not math.isfinite(value.real)
        or not math.isfinite(value.imag)
    ):
        raise ValueError("finite wave number and matching positive cell axes required")

    from scipy.special import spherical_jn

    z = value * lengths / 2
    phase = np.exp(1j * value * (origins + lengths / 2))
    moments = np.empty((len(origins), degree + 1), dtype=np.complex128)
    negative_real = value.imag == 0.0 and value.real < 0.0
    argument = -z if negative_real else z
    for ell in range(degree + 1):
        spherical = spherical_jn(ell, argument)
        if negative_real and ell % 2:
            spherical = -spherical
        moments[:, ell] = phase * (1j**ell) * spherical
    if value == 0:
        moments.fill(0.0)
        moments[:, 0] = 1.0
    return moments


class AnalyticMomentBoundaryReference:
    """Independent boundary-action reference built from closed-form 1D moments."""

    def __init__(self, layout, modes, *, face_inventory=None):
        from .directional_boundary import zvalue

        self.layout = layout
        self.modes = tuple(modes)
        if not self.modes:
            raise ValueError("analytic boundary reference requires frozen modes")
        self.by_side = {
            side: tuple(i for i, mode in enumerate(self.modes) if mode["side"] == side)
            for side in ("bottom", "top")
        }
        self.face_masks = None
        if face_inventory is not None:
            faces = tuple(tuple(face) for face in face_inventory)
            if not faces or len(set(faces)) != len(faces):
                raise ValueError("analytic reference requires unique selected faces")
            masks = {
                side: np.zeros((layout.nx, layout.ny), dtype=bool)
                for side in ("bottom", "top")
            }
            for side, i, j in faces:
                if side not in masks or not 0 <= i < layout.nx or not 0 <= j < layout.ny:
                    raise ValueError("analytic reference face is outside the layout")
                masks[side][i, j] = True
            self.face_masks = masks
        self.tables = {}
        for side, indices in self.by_side.items():
            selected = [self.modes[i] for i in indices]
            if not selected:
                self.tables[side] = (
                    np.empty((0, layout.nx * (layout.p + 1)), dtype=np.complex128),
                    np.empty((0, layout.ny * (layout.p + 1)), dtype=np.complex128),
                    np.empty(0, dtype=np.int64),
                    np.empty(0, dtype=np.int64),
                    np.empty(0, dtype=np.complex128),
                )
                continue
            x_values = [zvalue(mode["k_vector"][0]) for mode in selected]
            y_values = [zvalue(mode["k_vector"][1]) for mode in selected]
            x_unique = sorted(set(x_values), key=lambda z: (z.real, z.imag))
            y_unique = sorted(set(y_values), key=lambda z: (z.real, z.imag))
            fx = np.stack([
                legendre_exponential_moment_table(
                    -np.conj(k), layout.x[:-1], np.diff(layout.x), layout.p
                )
                for k in x_unique
            ]).reshape(len(x_unique), -1)
            fy = np.stack([
                legendre_exponential_moment_table(
                    -np.conj(k), layout.y[:-1], np.diff(layout.y), layout.p
                )
                for k in y_unique
            ]).reshape(len(y_unique), -1)
            x_lookup = {k: i for i, k in enumerate(x_unique)}
            y_lookup = {k: i for i, k in enumerate(y_unique)}
            ix = np.asarray([x_lookup[k] for k in x_values], dtype=np.int64)
            iy = np.asarray([y_lookup[k] for k in y_values], dtype=np.int64)
            zphase = np.asarray([
                np.exp(
                    -1j
                    * np.conj(zvalue(self.modes[i]["k_vector"][2]))
                    * self.modes[i]["reference_plane_nm"]
                )
                for i in indices
            ], dtype=np.complex128)
            self.tables[side] = (fx, fy, ix, iy, zphase)
        self.e = np.asarray([
            [zvalue(v) for v in mode["e_vector"][:2]] for mode in self.modes
        ], dtype=np.complex128)
        self.traction = np.asarray([
            [zvalue(v) for v in mode["traction_vector"][:2]] for mode in self.modes
        ], dtype=np.complex128)
        self.H = np.asarray(
            [mode["projection_denominator"] for mode in self.modes],
            dtype=np.float64,
        )
        if (
            not np.isfinite(self.e).all()
            or not np.isfinite(self.traction).all()
            or not np.isfinite(self.H).all()
            or np.any(self.H <= 0)
        ):
            raise ValueError("analytic reference modes require finite vectors and positive H")

    def project_components(self, trace):
        from .directional_boundary import _vector

        trace = _vector(trace, self.layout.rows, "boundary primal")
        out = np.zeros((len(self.modes), 2), dtype=np.complex128)
        for side, indices in self.by_side.items():
            if not indices:
                continue
            fx, fy, ix, iy, phase = self.tables[side]
            coeff = self.layout.field_coefficients(trace, side)
            if self.face_masks is not None:
                coeff *= self.face_masks[side][:, :, None, None, None]
            for component in (0, 1):
                grid = (
                    coeff[:, :, :, :, component]
                    .transpose(0, 2, 1, 3)
                    .reshape(fx.shape[1], fy.shape[1])
                )
                spectral = (fx @ grid) @ fy.T
                out[np.asarray(indices), component] = (
                    spectral[ix, iy] * phase
                )
        return out

    def scatter_components(self, values):
        values = np.asarray(values)
        if (
            values.shape != (len(self.modes), 2)
            or values.dtype != np.complex128
            or not np.isfinite(values).all()
        ):
            raise ValueError("boundary dual components shape/complex128/finite")
        out = np.zeros(self.layout.rows, dtype=np.complex128)
        for side, indices in self.by_side.items():
            if not indices:
                continue
            fx, fy, ix, iy, phase = self.tables[side]
            coeff = np.zeros(
                (self.layout.nx, self.layout.ny, self.layout.p + 1,
                 self.layout.p + 1, 2),
                dtype=np.complex128,
            )
            for component in (0, 1):
                spectral = np.zeros((len(fx), len(fy)), dtype=np.complex128)
                np.add.at(
                    spectral,
                    (ix, iy),
                    values[np.asarray(indices), component] * phase.conj(),
                )
                grid = (fx.conj().T @ spectral) @ fy.conj()
                coeff[:, :, :, :, component] = grid.reshape(
                    self.layout.nx,
                    self.layout.p + 1,
                    self.layout.ny,
                    self.layout.p + 1,
                ).transpose(0, 2, 1, 3)
            if self.face_masks is not None:
                coeff *= self.face_masks[side][:, :, None, None, None]
            out += self.layout.scatter_coefficients(coeff, side)
        return out

    def recover(self, trace):
        return np.sum(self.e.conj() * self.project_components(trace), axis=1) / self.H

    def modal_rhs(self, alpha):
        from .directional_boundary import _vector

        return self.scatter_components(
            -self.traction * _vector(alpha, len(self.modes), "port amplitudes")[:, None]
        )

    def apply(self, trace):
        amplitudes = np.sum(self.e.conj() * self.project_components(trace), axis=1) / self.H
        return self.modal_rhs(amplitudes)
