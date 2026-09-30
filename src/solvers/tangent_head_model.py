"""Reviewed real directional residual model and stable head compensation.

Only the original action, a small Hhat solve, and tall/thin decompositions are
used.  This is neither an exact VarPro nor a global Jacobian/normal equation.
"""

import numpy as np

from src.solvers.actual_loss_block_descent import qualified_audit


def bar_action(packet, ports, trace):
    original = packet.apply(np.r_[trace, np.zeros(40, np.complex128)])
    port = -np.linalg.solve(ports.H, original[packet.nt:])
    value = original[:packet.nt] + ports.C @ port
    return value, np.r_[trace, port]


def loss_resolution(points, bnorm):
    first = points[0]
    loss_differences = [abs(p['loss']-first['loss']) for p in points[1:]]
    residual_differences = [np.linalg.norm(p['bar_residual']-first['bar_residual']) for p in points[1:]]
    dr = max(residual_differences, default=0.)
    floor = 100*np.finfo(np.float64).eps*max(1., first['loss'])
    induced = (np.linalg.norm(first['bar_residual'])*dr + .5*dr**2)/bnorm**2
    return dict(delta_J=float(max(floor, max(loss_differences, default=0.), induced)),
                floor=float(floor), observed_loss_differences=loss_differences,
                observed_residual_differences=list(map(float, residual_differences)),
                induced_loss_scale=float(induced), strict_all_point_error_bound=False)


def fixed_head_scale(hidden, residual, response, bnorm, derivative):
    product = np.conj(response)*residual
    inner = float(np.sum(product).real)
    s = inner/bnorm**2
    curvature = float(np.vdot(response, response).real/bnorm**2)
    derivative_disagreement = abs(s+derivative)
    roundoff = 100*np.finfo(np.float64).eps*float(np.sum(np.abs(product)))/bnorm**2
    uncertainty = max(20*derivative_disagreement, roundoff)
    sign = 1 if s >= 0 else -1
    size = abs(s)/curvature if curvature > 0 else 0.
    bound = min(1e-4*max(1., np.linalg.norm(hidden)),
                .1*np.linalg.norm(residual)/max(np.linalg.norm(response), 1e-300))
    alpha = min(size, bound)
    pred = (abs(s)*alpha-.5*curvature*alpha**2)
    return dict(s=s, c=curvature, alpha_lin=size, sign=sign, alpha=float(alpha),
                pred=float(pred), uncertainty=float(uncertainty),
                derivative_disagreement=float(derivative_disagreement),
                dot_absolute_term_sum=float(np.sum(np.abs(product))),
                sign_trustworthy=bool(abs(s)>uncertainty and curvature>0))


def real_local_step(hidden_directions, head_directions, responses, residual):
    """Complex field response, but only REAL coefficients update real hidden."""
    columns = np.asarray(responses)
    if columns.ndim != 2 or not 1 <= columns.shape[1] <= 3:
        raise ValueError("one to three complex model columns required")
    norms = np.linalg.norm(columns, axis=0)
    if not np.isfinite(norms).all() or np.any(norms == 0):
        raise ValueError("zero/nonfinite joint response column")
    normalized = columns/norms
    matrix = np.vstack((normalized.real, normalized.imag))
    rhs = np.r_[residual.real, residual.imag]
    a_scaled, _, rank, singular = np.linalg.lstsq(matrix, rhs, rcond=1e-12)
    coefficients = a_scaled/norms
    if np.iscomplexobj(coefficients) or np.iscomplexobj(hidden_directions):
        raise ValueError("complex coefficients cannot update real hidden")
    return hidden_directions@coefficients, head_directions@coefficients, columns@coefficients, dict(
        real_coefficients=coefficients.tolist(), column_norms=norms.tolist(),
        rank=int(rank), singular_values=singular.tolist(), cond=1e-12,
        deterministic_unit_column_scaling=True, driver='numpy_lstsq_SVD', inverse_or_normal_equations=False)


def common_radius(hidden, head, dhidden, dhead):
    if np.iscomplexobj(dhidden) or not np.isfinite(dhidden).all() or not np.isfinite(dhead).all():
        raise ValueError("joint hidden step must remain finite and real")
    return float(min(1., 1e-4*max(1., np.linalg.norm(hidden))/max(np.linalg.norm(dhidden),1e-300),
                     .1*max(1., np.linalg.norm(head))/max(np.linalg.norm(dhead),1e-300)))


def predicted_gain(residual, change, bnorm):
    return float((np.vdot(residual, change).real-.5*np.vdot(change, change).real)/bnorm**2)


def accept_step(old, new, prediction, old_resolution, new_resolution, old_audit, new_audit):
    actual = old['loss']-new['loss']
    margin = max(1e-12, 20*max(old_resolution, new_resolution))
    ratio = actual/prediction if prediction > 0 else 0.
    accepted = (prediction > max(1e-12,100*old_resolution) and actual > margin
                and ratio >= .1 and qualified_audit(new_audit)
                and new_audit['native_relative'] <= 1.05*old_audit['native_relative'])
    return dict(accepted=bool(accepted), ared=float(actual), pred=float(prediction),
                ratio=float(ratio), acceptance_margin=float(margin),
                old_delta_J=float(old_resolution), trial_delta_J=float(new_resolution))


def compensation_solve(packet, ports, P, responses, old_A=None, heartbeat=None):
    """One nonpivoting Householder basis and one <=3 RHS GELSD solve."""
    from scipy.linalg import qr, svdvals, lstsq, solve_triangular
    from time import perf_counter
    started = perf_counter()
    columns=P.shape[1]
    if not 1<=columns<=1560 or P.shape[0]!=packet.nt or responses.shape[0]!=packet.nt:
        raise ValueError('bounded thin compensation inventory required')
    Z,R = qr(P, mode='economic', pivoting=False, check_finite=False)
    reassembly = np.linalg.norm(P-Z@R)/max(np.linalg.norm(P),1e-300)
    singular_P = svdvals(R, check_finite=False)
    rank_P = int(np.sum(singular_P > singular_P[0]*1e-12))
    if reassembly > 1e-10 or rank_P != columns:
        raise ValueError("current P QR/rank unsafe")
    paired = []
    if old_A is not None:
        A=old_A
        for j in (0,columns//2,columns-1):
            actual,_=bar_action(packet,ports,Z[:,j])
            paired.append(float(np.linalg.norm(actual-A[:,j])/max(np.linalg.norm(A[:,j]),1e-300)))
        if max(paired)>1e-10:
            raise ValueError("saved A no longer matches current deterministic QR")
    else:
        A=np.empty_like(Z,order='F')
        for j in range(columns):
            A[:,j],_=bar_action(packet,ports,Z[:,j])
            if heartbeat and (j%128==0 or j==columns-1):
                heartbeat('head_compensation_A', completed=j+1,total=columns)
    built=perf_counter()-started
    k,_,rank,singular_A=lstsq(A,responses,cond=1e-12,lapack_driver='gelsd',check_finite=False)
    if rank != columns:
        raise ValueError("current A numerical column rank unsafe")
    dgamma=solve_triangular(R,-k,lower=False,check_finite=False)
    triangular_defect=float(np.linalg.norm(R@dgamma+k)/max(np.linalg.norm(R@dgamma)+np.linalg.norm(k),1e-300))
    thin=responses-A@k
    ptrace=P@dgamma
    return dgamma,ptrace,thin,dict(rank_P=rank_P,rank_A=int(rank),
        P_singular_range=[float(singular_P[-1]),float(singular_P[0])],
        A_singular_range=[float(singular_A[-1]),float(singular_A[0])],
        QR_reassembly=float(reassembly), saved_A_three_original_checks=paired,
        head_compensation_norms=np.linalg.norm(dgamma,axis=0).tolist(),
        thin_residual_norms=np.linalg.norm(thin,axis=0).tolist(),
        compensation_triangular_operation_error=triangular_defect,
        compensation_sign='R_dot_gamma_EQUALS_MINUS_k',
        basis_seconds=built,total_seconds=perf_counter()-started,
        reused_same_hidden_A=old_A is not None,driver='gelsd',cond=1e-12,
        thin_decompositions=1,RHS_columns=responses.shape[1],
        head_gate_1e8='FAIL_UNCHANGED_NOT_VARPRO',
        P_bytes=P.nbytes,Z_bytes=Z.nbytes,R_bytes=R.nbytes,A_bytes=A.nbytes,
        no_explicit_inverse=True,no_normal_equations=True,no_global_factor=True)
