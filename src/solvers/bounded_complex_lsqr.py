"""Undamped complex LSQR with explicit checkpoints and no preconditioner.

Golub--Kahan bidiagonalization uses real norms and real plane rotations,
and the actual complex conjugate transpose. Neither a normal-equation matrix
nor any inverse is constructed. The caller owns the hard action/wall budget.
"""

import numpy as np


class LSQRState:
    """One complete undamped GK boundary; no operator is serialized."""

    version = 'complex-lsqr-gk-v1'

    def __init__(self, values):
        self.values = {k: (np.array(v, copy=True) if k in ('x', 'u', 'v', 'w') else v)
                       for k, v in values.items()}
        self.validate()

    @classmethod
    def initialize(cls, adjoint, rhs):
        rhs = np.asarray(rhs, dtype=np.complex128)
        beta = float(np.linalg.norm(rhs)); x = np.zeros_like(rhs)
        u = rhs / beta if beta else x.copy()
        v = adjoint(u) if beta else x.copy()
        alpha = float(np.linalg.norm(v))
        if alpha: v = v / alpha
        return cls(dict(iteration=0, x=x, u=u, v=v, w=v.copy(), alpha=alpha,
                        beta=beta, phibar=beta, rhobar=alpha, rhs_norm=beta,
                        terminated=bool(beta == 0 or alpha == 0)))

    @classmethod
    def restore(cls, values):
        # Scalars loaded from NPZ have zero-dimensional array type.
        values = dict(values)
        for key in ('iteration',): values[key] = int(values[key])
        for key in ('alpha', 'beta', 'phibar', 'rhobar', 'rhs_norm'): values[key] = float(values[key])
        values['terminated'] = bool(values['terminated'])
        return cls(values)

    def validate(self):
        a = self.values
        if set(a) != {'iteration','x','u','v','w','alpha','beta','phibar','rhobar','rhs_norm','terminated'}:
            raise ValueError('incomplete GK boundary')
        shape = a['x'].shape
        if len(shape) != 1 or any(a[k].shape != shape or a[k].dtype != np.complex128
                                  or not np.isfinite(a[k]).all() for k in ('x','u','v','w')):
            raise ValueError('invalid GK vector shape/dtype/finite')
        if a['iteration'] < 0 or any(not np.isfinite(a[k]) for k in ('alpha','beta','phibar','rhobar','rhs_norm')):
            raise ValueError('invalid GK scalar')
        if min(a['alpha'], a['beta'], a['rhs_norm']) < 0:
            raise ValueError('negative GK norm')
        if (a['alpha'] == 0 or a['beta'] == 0) and not a['terminated']:
            raise ValueError('zero norm must terminate')

    def export(self):
        return {k: (v.copy() if isinstance(v,np.ndarray) else v) for k,v in self.values.items()}

    def step(self, action, adjoint):
        a = self.values
        if a['terminated']: return False
        u = action(a['v']) - a['alpha'] * a['u']
        beta = float(np.linalg.norm(u)); v = a['v']; alpha = a['alpha']
        if beta > 0:
            u /= beta
            v = adjoint(u) - beta * v
            alpha = float(np.linalg.norm(v))
            if alpha > 0: v /= alpha
        rho = float(np.hypot(a['rhobar'], beta))
        if rho == 0:
            a['terminated'] = True
            return False
        cosine, sine = a['rhobar']/rho, beta/rho
        theta, rhobar = sine*alpha, -cosine*alpha
        phi, phibar = cosine*a['phibar'], sine*a['phibar']
        a['x'] += (phi/rho)*a['w']
        w = v - (theta/rho)*a['w']
        a.update(iteration=a['iteration']+1, u=u, v=v, w=w, alpha=alpha,
                 beta=beta, phibar=phibar, rhobar=rhobar,
                 terminated=bool(beta == 0 or alpha == 0))
        self.validate()
        return True


def lsqr_steps(action, adjoint, rhs, *, state_callback=None, resume_state=None):
    """Yield (iteration,x,estimated residual) from zero; caller decides Gates."""
    state = LSQRState.initialize(adjoint,rhs) if resume_state is None else LSQRState.restore(resume_state)
    if state.values['terminated']:
        a = state.values
        yield a['iteration'],a['x'].copy(),abs(a['phibar'])
        return
    while not state.values['terminated']:
        advanced = state.step(action,adjoint)
        a = state.values
        if state_callback is not None:
            # Preserve the historical callback schema and operation ordering.
            state_callback({k:v for k,v in state.export().items() if k not in ('rhs_norm','terminated')})
        yield a['iteration'], a['x'].copy(), abs(a['phibar'])
        if not advanced: return
