"""Offline eight-direction diagnosis; no solver state or learned coefficients.

Each direction is a homogeneous correction. The original affine internal
particular solution and port RHS never enter these direction actions.
"""
from time import perf_counter

import numpy as np
from scipy.linalg import lstsq, qr

FAMILY = 'FROZEN_LOCAL8_RESIDUAL_DIRECTION_DIAGNOSTIC'
EPS = np.finfo(np.float64).eps
RANK_THRESHOLD = 1e-12


def relative(error, scale):
    if scale == 0:
        return 0. if error == 0 else None
    return float(error/scale)


def complex_value(z):
    return dict(real=float(np.real(z)), imag=float(np.imag(z)))


def block_response(images, rows, residual):
    """Cross products are reporting only, never a normal-equation solve."""
    report = []
    for i, ids in enumerate(rows):
        X = images[ids]
        norms = np.linalg.norm(X, axis=0)
        cross = X.conj().T @ X
        coherent = np.sum(X, axis=1)
        norm_sq = float(np.linalg.norm(coherent)**2)
        diagonal_sq = float(np.real(np.trace(cross)))
        off_diagonal = float(2*sum(cross[j,k].real for j in range(8) for k in range(j+1,8)))
        report.append(dict(target_block=i, source_blocks=list(range(8)),
            response_norms=norms.tolist(), coherent_sum_norm=float(np.linalg.norm(coherent)),
            coherent_sum_norm_sq=norm_sq, sum_individual_norm_sq=diagonal_sq,
            twice_real_cross_sum=off_diagonal,
            cross_square_identity_operation_relative=relative(abs(norm_sq-diagonal_sq-off_diagonal),
                diagonal_sq+abs(off_diagonal)),
            complex_cross_products=[[complex_value(z) for z in line] for line in cross],
            cancellation_ratio=relative(float(np.linalg.norm(coherent)),float(sum(norms))),
            original_target_residual_norm=float(np.linalg.norm(residual[ids]))))
    return report


def diagnose(residual, local, action, *, bnorm, operation_scale=None,
             count=lambda key,n=1: None, guard=lambda: None):
    """One L8, eight images, exactly two independent action recombinations."""
    began = perf_counter()
    r = np.asarray(residual, dtype=np.complex128)
    if r.shape != (local.n,) or not np.isfinite(r).all() or not bnorm > 0:
        raise ValueError('diagnostic residual inventory/nonfinite/normalization')
    q = local.apply(r)
    directions = np.zeros((local.n,8),dtype=np.complex128,order='F')
    images = np.empty_like(directions)
    scales = []
    diagonal = []
    for j,ids in enumerate(local.rows):
        guard(); directions[ids,j] = q[ids]
        images[:,j] = action(directions[:,j])
        scale = float(operation_scale(directions[:,j]) if operation_scale else np.linalg.norm(images[:,j]))
        if not np.isfinite(scale) or scale < 0:raise ValueError('invalid operation scale')
        scales.append(scale)
        error = np.linalg.norm(images[ids,j]-r[ids])
        diagonal.append(dict(block=j, error_norm=float(error),
            operation_scale=max(scale,float(np.linalg.norm(r[ids]))),
            operation_relative=relative(float(error),max(scale,float(np.linalg.norm(r[ids]))))))
    v = np.sum(images,axis=1)
    actual_v = action(q)
    rnorm,vnorm = float(np.linalg.norm(r)),float(np.linalg.norm(v))
    norms = np.linalg.norm(images,axis=0)
    floors = 64*EPS*np.array(scales)
    resolved = norms > floors
    alpha = np.vdot(v,r)/(vnorm*vnorm) if vnorm else 0j
    coef = np.zeros(8,complex)
    rank = 0; singular = []; qr_error = ortho_error = 0.
    stationarity = 0.; decomposition_seconds = 0.
    nonzero = norms > 0
    if np.any(nonzero):
        count('thin_decompositions');started=perf_counter()
        balanced = images[:,nonzero]/norms[nonzero]
        Q,R = qr(balanced,mode='economic',pivoting=False,check_finite=False)
        # Only the <=8 column coordinate system is decomposed. Empty residues
        # from GELSD are ignored; every residual below is explicitly recomputed.
        beta,_,rank,svals = lstsq(R,Q.conj().T@r,cond=RANK_THRESHOLD,
            lapack_driver='gelsd',check_finite=False)
        coef[nonzero] = beta/norms[nonzero]
        singular = svals.tolist()
        qr_error = float(np.linalg.norm(Q@R-balanced)/np.linalg.norm(balanced))
        ortho_error = float(np.linalg.norm(Q.conj().T@Q-np.eye(Q.shape[1]))/np.sqrt(Q.shape[1]))
        err = r-images@coef
        stationarity = relative(float(np.linalg.norm(balanced.conj().T@err)),
            float(np.linalg.norm(balanced)*(rnorm+np.linalg.norm(images@coef))))
        decomposition_seconds = perf_counter()-started
    actual_best = action(directions@coef)
    eta_unit = relative(float(np.linalg.norm(r-v)),rnorm)
    eta1 = relative(float(np.linalg.norm(r-alpha*v)),rnorm)
    eta8 = relative(float(np.linalg.norm(r-images@coef)),rnorm)
    margin = 1e-10
    inequality = rnorm==0 or (eta8<=eta1+margin and eta1<=min(1.,eta_unit)+margin)
    pair_scale = float(sum(scales))
    unit_difference = float(np.linalg.norm(actual_v-v))
    best_difference = float(np.linalg.norm(actual_best-images@coef))
    pairs = dict(unit=dict(error_norm=unit_difference,
            full_b_relative=unit_difference/bnorm,current_r_relative=relative(unit_difference,rnorm),
            operation_relative=relative(unit_difference,pair_scale)),
        best=dict(error_norm=best_difference,
            full_b_relative=best_difference/bnorm,current_r_relative=relative(best_difference,rnorm),
            operation_relative=relative(best_difference,float(np.dot(np.abs(coef),scales)))))
    gates = dict(diagonal=all(x['operation_relative'] is not None and x['operation_relative']<=1e-10 for x in diagonal),
        recombination=all(x['full_b_relative']<=1e-11 and x['operation_relative'] is not None and x['operation_relative']<=1e-10 for x in pairs.values()),
        qr=qr_error<=1e-10 and ortho_error<=1e-10,
        stationarity=stationarity is not None and stationarity<=1e-8,inequality=inequality,
        numerical_full_direction_rank=rank==8,
        columns_resolved=bool(np.all(resolved)),
        whole_response_resolved=bool(np.linalg.norm(images)>64*EPS*np.linalg.norm(scales)))
    trustworthy = all(gates.values()) and rnorm>0
    metrics = dict(status='DIAGNOSTIC_COMPLETE' if trustworthy else 'NUMERICALLY_UNRESOLVED',
        gates=gates,trustworthy=trustworthy,eta_unit=eta_unit,eta1=eta1,eta8=eta8,
        true_eta_unit=relative(float(np.linalg.norm(r-actual_v)),rnorm),
        true_eta8=relative(float(np.linalg.norm(r-actual_best)),rnorm),
        residual_norm=rnorm,full_physical_b_norm=bnorm,alpha=complex_value(alpha),
        coefficients=[complex_value(c) for c in coef],coefficient_norm=float(np.linalg.norm(coef)),
        response_column_norms=norms.tolist(),operation_scales=scales,roundoff_floors=floors.tolist(),
        operation_scale_role='conservative original contraction magnitude proxy; not a full forward-error bound',
        resolved_columns=resolved.tolist(),rank=int(rank),singular_values=singular,
        rank_threshold=RANK_THRESHOLD,driver='gelsd',column_norm_equilibration=True,
        thin_residual_explicitly_recomputed=True,QR_relative=qr_error,orthogonality_relative=ortho_error,
        stationarity_operation_relative=stationarity,comparison_margin=margin,
        diagonal_witnesses=diagonal,independent_recombination=pairs,
        block_response=block_response(images,local.rows,r),
        decomposition_seconds=decomposition_seconds,diagnostic_seconds=perf_counter()-began,
        new_solver_state=False,nonlinear_residual_dependent_coefficients=True)
    arrays=dict(directions=directions,images=images,coefficients=coef,
        local_q=q,diagnostic_residual=r-actual_best)
    return metrics,arrays


def decision(rows):
    finals = rows[-2:]
    if len(finals)!=2 or not all(r['trustworthy'] for r in finals):return 'NUMERICALLY_UNRESOLVED'
    if all(r['eta8']<=.5 and r['eta8']<=.5*r['eta1'] for r in finals):return 'BLOCK_DIRECTION_COMBINATION_SIGNAL'
    if all(r['eta8']>=.9 for r in finals):return 'EIGHT_DIRECTIONS_WEAK'
    return 'STATE_DEPENDENT_INCONCLUSIVE'
