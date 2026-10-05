"""Minimal fixed-phase mathematical closure from frozen Task42extra V20.

Donor 8d617d4d206b08f38279320b67188db1b8ccd301. Its build_model,
materials, geometry, recovery and training workflow are deliberately excluded.
The new representation is g times a periodic Nedelec envelope, not a
projection of the physical field back into the polynomial space.
"""
import numpy as np


def carrier(cfg, enabled=True):
    k = np.asarray([cfg.kx, cfg.ky, 0], dtype=complex)
    if np.max(np.abs(k.imag)) > 1e-14 or not np.all(np.isfinite(k)):
        raise ValueError('fixed phase requires a finite real transverse wavevector')
    return k.real if enabled else np.zeros(3)


def physical_fields(mesh, envelope, kappa):
    import ufl
    from petsc4py import PETSc
    k = ufl.as_vector(tuple(PETSc.ScalarType(v) for v in kappa))
    g = ufl.exp(1j * ufl.dot(k, ufl.SpatialCoordinate(mesh)))
    return g * envelope, g * (ufl.curl(envelope) + 1j * ufl.cross(k, envelope))


def envelope_configuration(cfg, kappa):
    """Change only the constraint phases; retain physical incidence/modes."""
    import copy
    class EnvelopeConfig(type(cfg)):
        @property
        def floquet_phase_x(self):
            return np.exp(1j * (self.kx-kappa[0]) * (self.x_max-self.x_min))

        @property
        def floquet_phase_y(self):
            return np.exp(1j * (self.ky-kappa[1]) * (self.y_max-self.y_min))
    result = copy.copy(cfg)
    result.__class__ = EnvelopeConfig
    return result


def port_coordinate_scales(fe_rows, H, phase):
    """Exact reference-plane coordinate change; no clipping or pseudoinverse."""
    H = np.asarray(H, complex); phase = np.asarray(phase, complex)
    if H.shape != phase.shape or np.any(H == 0) or np.any(phase == 0):
        raise ValueError('noninvertible port coordinates')
    right = np.r_[np.ones(fe_rows), 1/phase]
    left = np.r_[np.ones(fe_rows), phase/H]
    if not np.all(np.isfinite(right)) or not np.all(np.isfinite(left)):
        raise ValueError('unsafe port coordinate range')
    return left, right
