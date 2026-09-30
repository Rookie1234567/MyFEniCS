"""Undamped complex LSQR with explicit checkpoints and no preconditioner.

Golub--Kahan bidiagonalization uses real norms and real plane rotations,
and the actual complex conjugate transpose. Neither a normal-equation matrix
nor any inverse is constructed. The caller owns the hard action/wall budget.
"""

import numpy as np


def lsqr_steps(action, adjoint, rhs, *, state_callback=None):
    """Yield (iteration,x,estimated residual) from zero; caller decides Gates."""
    rhs = np.asarray(rhs, dtype=np.complex128)
    x = np.zeros_like(rhs)
    beta = float(np.linalg.norm(rhs))
    if beta == 0:
        yield 0, x, 0.0
        return
    u = rhs / beta
    v = adjoint(u)
    alpha = float(np.linalg.norm(v))
    if alpha == 0:
        yield 0, x, beta
        return
    v = v / alpha
    w = v.copy()
    phibar, rhobar = beta, alpha
    iteration = 0
    while True:
        u = action(v) - alpha * u
        beta = float(np.linalg.norm(u))
        if beta > 0:
            u /= beta
            v = adjoint(u) - beta * v
            alpha = float(np.linalg.norm(v))
            if alpha > 0:
                v /= alpha
        rho = float(np.hypot(rhobar, beta))
        if rho == 0:
            yield iteration, x.copy(), abs(phibar)
            return
        cosine, sine = rhobar / rho, beta / rho
        theta, rhobar = sine * alpha, -cosine * alpha
        phi, phibar = cosine * phibar, sine * phibar
        x += (phi / rho) * w
        w = v - (theta / rho) * w
        iteration += 1
        if state_callback is not None:
            state_callback(dict(iteration=iteration, x=x.copy(), u=u.copy(),
                                v=v.copy(), w=w.copy(), alpha=alpha, beta=beta,
                                phibar=phibar, rhobar=rhobar))
        yield iteration, x.copy(), abs(phibar)
        if beta == 0 or alpha == 0:
            return
