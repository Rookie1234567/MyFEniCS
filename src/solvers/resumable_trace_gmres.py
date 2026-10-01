"""One SciPy complex GMRES(64) correction cycle on the original bar S.

Older qualified SciPy names relative tolerance ``tol`` rather than ``rtol``.
Both are set to zero; the fixed absolute physical-RHS threshold is unchanged.
"""
import inspect
import numpy as np
import scipy
from scipy.sparse.linalg import LinearOperator,gmres


def signature_record(restart=64):
    if restart not in (64,256):raise ValueError('only registered GMRES restart lengths 64/256')
    return dict(scipy_version=scipy.__version__,signature=str(inspect.signature(gmres)),
                relative_tolerance_keyword='rtol' if 'rtol' in inspect.signature(gmres).parameters else 'tol',
                relative_tolerance=0.,restart=restart,maxiter=1,callback_type='pr_norm',preconditioner=None)


def correction_cycle(action, base, rhs, physical_bnorm, callback=None, *, restart=64):
    contract=signature_record(restart)
    base=np.asarray(base);rhs=np.asarray(rhs)
    if base.ndim!=1 or rhs.shape!=base.shape or not np.isfinite(base).all():
        raise ValueError('one-dimensional finite GMRES trace/RHS required')
    rb=rhs-action(base)
    if not np.isfinite(rb).all() or not physical_bnorm>0:raise ValueError('invalid GMRES correction')
    contract.update(physical_bnorm=float(physical_bnorm),absolute_tolerance=float(1e-8*physical_bnorm))
    if np.linalg.norm(rb)==0:return base.copy(),dict(info=0,inner_iterations=0,zero_rhs=True,**contract)
    iterations=[]
    def record(value):
        iterations.append(float(value))
        if callback is not None:callback(float(value),len(iterations))
    operator=LinearOperator((len(base),len(base)),matvec=action,dtype=np.complex128)
    relative=contract['relative_tolerance_keyword']
    delta,info=gmres(operator,rb,restart=restart,maxiter=1,callback_type='pr_norm',M=None,
                     atol=1e-8*physical_bnorm,callback=record,**{relative:0.})
    if info<0 or not np.isfinite(delta).all():raise ValueError('GMRES negative status or nonfinite correction')
    return base+delta,dict(info=int(info),inner_iterations=len(iterations),
                          estimated_history=iterations,zero_rhs=False,**contract)
