"""Opt-in complete Ckappa tensors for scalar affine axis-aligned hexes.

The six-Gram implementation remains unchanged. Nine additional reference
integrals supply both conjugate cross terms and the kappa-square term.
No orientation or MPC transformation is performed here.
"""
from time import perf_counter
import basix
import numpy as np
from .hcurl_affine_isotropic_tensor import (
    AffineIsotropicMaxwellTensorFactory, AffineIsotropicMaxwellTensorSpec,
)


class AffinePhaseReferenceTensor:
    backend = 'AFFINE_PHASE_REFERENCE_TENSOR'

    def __init__(self, element, *, kappa, k0, epsilon_by_tag, mu=1., q):
        started = perf_counter()
        if not isinstance(element,basix.finite_element.FiniteElement):
            element=basix.finite_element.FiniteElement(element)
        kk = np.asarray(kappa)
        if kk.shape != (3,) or np.iscomplexobj(kk) or not np.all(np.isfinite(kk)):
            raise ValueError('constant real three-component kappa required')
        if not np.isscalar(mu) or not np.isfinite(mu) or mu == 0:
            raise ValueError('constant scalar nonzero mu required; no PML')
        self.kappa = kk.astype(float); self.k0 = float(k0); self.mu = complex(mu)
        self.epsilon = {int(k): complex(v) for k, v in epsilon_by_tag.items()}
        self.base = AffineIsotropicMaxwellTensorFactory(element,
            AffineIsotropicMaxwellTensorSpec(1 / self.mu,
                {k: -self.k0**2*v for k, v in self.epsilon.items()}, q))
        points, weights = basix.make_quadrature(element.cell_type, q,
            polyset_type=element.polyset_type)
        tab = element.tabulate(1, points); value = tab[0]
        curl = np.stack((tab[2,:,:,2]-tab[3,:,:,1],
            tab[3,:,:,0]-tab[1,:,:,2], tab[1,:,:,1]-tab[2,:,:,0]), axis=2)
        self.mass = {(a,a): self.base.mass_components[a] for a in range(3)}
        self.mass.update({(a,c): np.ascontiguousarray(value[:,:,a].T @
            (weights[:,None]*value[:,:,c])) for a in range(3) for c in range(a+1,3)})
        self.cross = {(a,c): np.ascontiguousarray(curl[:,:,a].T @
            (weights[:,None]*value[:,:,c])) for a in range(3) for c in range(3) if a != c}
        for m in (*self.mass.values(), *self.cross.values()):
            if not np.all(np.isfinite(m)): raise ValueError('nonfinite reference integral')
            m.flags.writeable = False
        self.element = element
        self.build_seconds = perf_counter()-started
        self.audit = dict(self.base.audit, backend=self.backend, kappa=self.kappa,
            k0=self.k0, mu=self.mu, epsilon_by_tag=self.epsilon,
            reference_component_count=15, reference_component_bytes=sum(m.nbytes for m in
            (*self.base.curl_components,*self.mass.values(),*self.cross.values())),
            total_build_seconds=self.build_seconds, original_six_gram_semantics_unchanged=True,
            direction_MPC_applied_here=False)

    def tensor(self, *, tag, widths, return_scale=False):
        h = np.asarray(widths, float)
        if h.shape != (3,) or not np.all(np.isfinite(h)) or np.any(h <= 0):
            raise ValueError('positive exact axis-aligned widths required')
        if int(tag) not in self.epsilon: raise ValueError('unknown scalar material tag')
        d = float(np.prod(h)); b = h/d
        kx,ky,kz = self.kappa
        Q = np.asarray([[0.,-kz,ky],[kz,0.,-kx],[-ky,kx,0.]])/h[None,:]
        out = np.zeros((self.element.dim,self.element.dim), complex); scale = 0.
        def add(matrix, coefficient):
            nonlocal scale
            if coefficient != 0:
                out[:] += coefficient*matrix
                scale += abs(coefficient)*float(np.linalg.norm(matrix))
        for a in range(3):
            add(self.base.curl_components[a], d/self.mu*b[a]**2)
            for c in range(3):
                for e in range(3):
                    m = self.mass[c,e] if c <= e else self.mass[e,c].T
                    add(m, d/self.mu*Q[a,c]*Q[a,e])
                if c != a:
                    coeff = 1j*d/self.mu*b[a]*Q[a,c]
                    add(self.cross[a,c], coeff); add(self.cross[a,c].T, -coeff)
        for c in range(3): add(self.mass[c,c], -d*self.k0**2*self.epsilon[int(tag)]/h[c]**2)
        return (out,scale) if return_scale else out


def axis_widths(coordinates):
    """Reject non-diagonal affine maps rather than approximate them."""
    x = np.asarray(coordinates,float).reshape(8,3)
    ref = basix.cell.geometry(basix.CellType.hexahedron)
    h = x.max(axis=0)-x.min(axis=0)
    if np.any(h <= 0) or not np.array_equal(x, x.min(axis=0)+ref*h):
        # Roundoff tolerance is only a geometry validity check; h is never rounded.
        if np.any(h <= 0) or np.max(np.abs(x-(x.min(axis=0)+ref*h))) > 1e-13*max(float(h.max()),1.):
            raise ValueError('axis-aligned affine geometry required')
    return h
