"""Local full-column port functionals; no volume operator or inverse.

The caller supplies actual integrated covariant tangential basis functions,
physical outgoing wavevectors, polarization and the original whole-cell H.
"""

import numpy as np


def local_port_rows(integral, k, electric, normal, *, original_area, reference_z):
    integral = np.asarray(integral, np.complex128)
    k, electric, normal = (np.asarray(v) for v in (k, electric, normal))
    if (
        integral.ndim != 2
        or integral.shape[1] != 2
        or any(v.shape != (3,) for v in (k, electric, normal))
        or not all(np.isfinite(v).all() for v in (integral, k, electric, normal))
        or original_area <= 0
        or np.linalg.norm(normal) != 1
    ):
        raise ValueError("LOCAL_PORT_PHYSICAL_LAYOUT")
    traction = np.cross(1j * np.cross(k, electric), normal)
    B = -integral @ traction[:2]
    D = integral.conj() @ electric[:2].conj()
    H = (
        original_area
        * np.vdot(electric[:2], electric[:2]).real
        * abs(np.exp(1j * k[2] * reference_z)) ** 2
    )
    if not np.isfinite(H) or H <= 0:
        raise ValueError("ORIGINAL_PORT_H_NOT_REPRESENTABLE")
    return B, D, float(H)


def port_direction_actions(B, D, H, coefficients, load):
    """Full local trace forward/adjoint and nonzero original port load."""
    B, D = np.asarray(B), np.asarray(D)
    c, load = np.asarray(coefficients), np.asarray(load)
    if B.shape != D.shape or c.shape[-1] != B.shape[-1] or load.shape != H.shape:
        raise ValueError("LOCAL_PORT_ACTION_LAYOUT")
    alpha = (D @ c.T + load[:, None]) / H[:, None]
    return dict(forward=B @ c.T, projection=alpha, adjoint=B.conj().T @ load)
