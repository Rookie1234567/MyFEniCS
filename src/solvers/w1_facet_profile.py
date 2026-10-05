"""One fixed opt-in q60 phase subdivision, on the same native FE face.

No q/p/mesh scan and no amplitude pruning. The unchanged full polynomial,
physical Piola factors and original phase are evaluated before contraction.
"""

import math
import numpy as np
from numpy.polynomial.legendre import legvander

NATIVE = "q60_native"
SUBDIVIDED = "q60_phase_subdivision_v28"


def subdivision_count(omega):
    if not np.isfinite(omega) or abs(complex(omega).imag) > 0:
        raise ValueError("W28_REAL_TANGENTIAL_PHASE")
    necessary = max(1, math.ceil(abs(float(np.real(omega))) / (4 * math.pi)))
    return 1 << (necessary - 1).bit_length()


def q60_moments(omega, p, rule, weights, subdivisions):
    if subdivisions != subdivision_count(omega):
        raise ValueError("W28_MINIMAL_FIXED_SUBDIVISION")
    out = np.zeros(p + 1, np.complex128)
    for j in range(subdivisions):
        t = (j + np.asarray(rule)) / subdivisions
        out += (
            (np.asarray(weights) / subdivisions) * np.exp(1j * omega * t)
        ) @ legvander(2 * t - 1, p)
    return out


class ProfiledFacet:
    def __init__(self, original, profile):
        if profile not in (NATIVE, SUBDIVIDED):
            raise ValueError("W28_FIXED_Q60_PROFILE")
        self.original, self.profile = original, profile
        self.cache = {}
        import basix

        rule, self.weights = basix.make_quadrature(basix.CellType.interval, 60)
        self.rule = rule[:, 0]

    def __getattr__(self, name):
        return getattr(self.original, name)

    def moment(self, omega):
        omega = float(omega)
        if omega not in self.cache:
            self.cache[omega] = q60_moments(
                omega, self.p, self.rule, self.weights, subdivision_count(omega)
            )
        return self.cache[omega]

    def integral_native(self, side, k, J, origin, q):
        if q != 60:
            raise ValueError("W28_NO_Q_SCAN")
        if self.profile == NATIVE:
            return self.original.integral_native(side, k, J, origin, q)
        if (
            np.any(np.asarray(k)[:2].imag != 0)
            or not np.array_equal(J, np.diag(np.diag(J)))
            or np.any(np.diag(J) <= 0)
        ):
            raise ValueError("W28_AFFINE_FACE_REQUIRED")
        ix, iy = self.moment(k[0].real * J[0, 0]), self.moment(k[1].real * J[1, 1])
        value = np.einsum(
            "a,b,abjc->jc", ix, iy, self.coefficients[side], optimize=True
        )
        value *= np.array([J[1, 1], J[0, 0]])
        pos = np.asarray(origin).copy()
        pos[2] += J[2, 2] if side == "top" else 0
        phase = np.exp(1j * np.dot(k, pos))
        if not np.isfinite(phase) or phase == 0:
            raise ValueError("W28_EXPONENTIAL_REPRESENTATION")
        return np.ascontiguousarray(value * phase, np.complex128)

    def integral(self, side, k, J, origin, q):
        return self.integral_native(side, k, J, origin, q)[self.active[side]]


def profiled_action(layout, modes, profile, q=60):
    from src.solvers.directional_boundary import DirectionalBoundaryAction, zvalue

    action = DirectionalBoundaryAction(
        layout, modes, q, face_inventory=(("top", 100, 1), ("bottom", 100, 1))
    )
    if profile == NATIVE:
        return action
    if profile != SUBDIVIDED:
        raise ValueError("W28_FIXED_Q60_PROFILE")
    # Keep the original contraction/scatter/project/adjoint APIs. Replace only
    # their two one-dimensional q60 moment tables with the declared profile.
    for side, indices in action.by_side.items():
        oldx, oldy, ix, iy, zphase = action.tables[side]
        matrices = []
        for axis, coords in enumerate((layout.x, layout.y)):
            ks = sorted(
                {zvalue(modes[i]["k_vector"][axis]) for i in indices},
                key=lambda z: (z.real, z.imag),
            )
            table = []
            for k in ks:
                row = []
                for origin, width in zip(coords[:-1], np.diff(coords), strict=True):
                    omega = -k.conjugate().real * width
                    value = layout.polynomial.moment(omega) * np.exp(
                        -1j * k.conjugate() * origin
                    )
                    row.append(value)
                table.append(np.array(row).ravel())
            matrices.append(np.array(table, np.complex128))
        if matrices[0].shape != oldx.shape or matrices[1].shape != oldy.shape:
            raise ValueError("W28_UNCHANGED_DIRECTIONAL_LAYOUT")
        action.tables[side] = (matrices[0], matrices[1], ix, iy, zphase)
    return action
