"""Small serial array diagnostics; callbacks supply the unchanged FE operators.

Vectors are independent-coordinate primal errors unless explicitly called q
or residual. Callback outputs are copied immediately, including borrowed FE
action buffers. No matrix of a nonlinear PC is constructed.
"""
import numpy as np


def copied_apply(action, x):
    y = np.array(action(x), dtype=np.complex128, copy=True)
    if y.ndim != 1 or not np.isfinite(y).all():
        raise ValueError('diagnostic action must return a finite vector')
    return y


def metric_square(mass, x):
    mx = copied_apply(mass, x)
    value = np.vdot(x, mx)
    scale = max(np.linalg.norm(x)*np.linalg.norm(mx), np.finfo(float).tiny)
    if abs(value.imag) > 1e-10*scale or value.real < -1e-10*scale:
        raise ValueError('metric is not Hermitian positive on this vector')
    return float(max(0, value.real))


def component_diagnostics(components, x):
    """Euclidean dual-component norms/cross terms, never field energies."""
    vectors = {name: copied_apply(action, x) for name, action in components.items()}
    names = list(vectors)
    gram = np.array([[np.vdot(vectors[a], vectors[b]) for b in names] for a in names])
    total = sum(vectors.values())
    return dict(names=names, norms={k: float(np.linalg.norm(v)) for k,v in vectors.items()},
                gram=gram, sum_vector=total, vectors=vectors, sum_norm=float(np.linalg.norm(total)),
                cancellation_ratio=float(sum(np.linalg.norm(v) for v in vectors.values()) /
                    max(np.linalg.norm(total), np.finfo(float).tiny)),
                norm_role='dual coefficient Euclidean; basis-scale dependent')


def project_error(prolong, adjoint, mass, diagonal, e, *, rtol=1e-10, max_it=256,
                  checkpoint=lambda: None):
    """One fixed-diagonal CG solve of P^H M0 P, with explicit final checks.

    The callbacks and diagonal live on independent coordinates: there are no
    artificial identity rows in the metric. A failed solve is retained as an
    approximate representation, and cannot demonstrate space inadequacy.
    """
    diagonal = np.asarray(diagonal)
    if np.any(diagonal.imag != 0) or not np.isfinite(diagonal).all() or np.any(diagonal.real <= 0):
        raise ValueError('projection requires a positive finite real diagonal')
    def operator(c):
        return copied_apply(adjoint, copied_apply(mass, copied_apply(prolong, c)))
    me = copied_apply(mass, e)
    b = copied_apply(adjoint, me)
    if b.shape != diagonal.shape:
        raise ValueError('coarse diagonal/transfer shape mismatch')
    c = np.zeros_like(b)
    r = b.copy()
    z = r/diagonal.real
    p = z.copy()
    rz = np.vdot(r,z)
    bnorm = float(np.linalg.norm(b))
    count, reason = 0, 'iteration_limit'
    for count in range(1, max_it+1):
        checkpoint()
        if np.linalg.norm(r) <= rtol*bnorm:
            count -= 1
            reason = 'recursive_tolerance'
            break
        ap = operator(p)
        pap = np.vdot(p,ap)
        if pap.real <= 0 or abs(pap.imag) > 1e-10*abs(pap):
            reason = 'nonpositive_or_nonhermitian_cg'
            count -= 1
            break
        alpha = rz/pap.real
        c += alpha*p
        r -= alpha*ap
        z = r/diagonal.real
        next_rz = np.vdot(r,z)
        p = z + (next_rz/rz)*p
        rz = next_rz
    parallel = copied_apply(prolong,c)
    perpendicular = np.asarray(e)-parallel
    mparallel = copied_apply(mass,parallel)
    mperp = me-mparallel
    explicit = copied_apply(adjoint,mperp)
    residual = float(np.linalg.norm(explicit)/max(bnorm,np.finfo(float).tiny))
    e2 = metric_square(mass,e)
    parallel2 = metric_square(mass,parallel)
    perp2 = metric_square(mass,perpendicular)
    cross = np.vdot(parallel,mperp)
    pythagorean = float(abs(e2-parallel2-perp2)/max(e2,np.finfo(float).tiny))
    # The equation residual checks all p4 directions, not just parallel itself.
    closed = residual <= rtol and pythagorean <= 1e-9
    return dict(status='PROJECTION_CLOSED' if closed else 'PROJECTION_UNRESOLVED',
                coarse=c, parallel=parallel, perpendicular=perpendicular,
                iterations=count, exit_reason=reason, equation_relative_residual=residual,
                orthogonality_relative_residual=residual, parallel_perp_inner=cross,
                pythagorean_relative_defect=pythagorean,
                eta_space=float(np.sqrt(perp2/max(e2,np.finfo(float).tiny))),
                error_energy=e2, parallel_energy=parallel2, perpendicular_energy=perp2,
                interpretation='measured projection' if closed else 'approximation upper bound only')


def correction_diagnostics(action, mass, e, q, direction):
    """Compare an existing direction with e; MR minimizes original q residual."""
    applied = copied_apply(action,direction)
    qnorm_raw = float(np.linalg.norm(q))
    qnorm = max(qnorm_raw,np.finfo(float).tiny)
    anorm = np.linalg.norm(applied)
    alpha = (np.vdot(applied/anorm,q)/anorm) if anorm else 0j
    e2 = metric_square(mass,e)
    unit_energy = metric_square(mass,e-direction)
    mr_energy = metric_square(mass,e-alpha*direction)
    return dict(alpha=complex(alpha),applied_direction=applied,q_norm=qnorm_raw,
                original_error_energy=e2,unit_remaining_energy=unit_energy,mr_remaining_energy=mr_energy,
                unit_field_ratio=float(np.sqrt(unit_energy/max(e2,np.finfo(float).tiny))),
                mr_field_ratio=float(np.sqrt(mr_energy/max(e2,np.finfo(float).tiny))),
                unit_true_residual_ratio=float(np.linalg.norm(q-applied)/qnorm),
                mr_true_residual_ratio=float(np.linalg.norm(q-alpha*applied)/qnorm))


def coarse_diagnostics(action, mass, prolong, adjoint, solve, e, projection):
    """Reuse one dG for the error decomposition; one extra coarse identity solve."""
    q = copied_apply(action,e)
    coarse = copied_apply(solve,copied_apply(adjoint,q))
    dg = copied_apply(prolong,coarse)
    result = correction_diagnostics(action,mass,e,q,dg)
    parallel,perp = projection['parallel'],projection['perpendicular']
    left = result['unit_remaining_energy']
    right = metric_square(mass,perp)+metric_square(mass,parallel-dg)
    result.update(decomposition_left=left,decomposition_right=right,
                  decomposition_relative_defect=float(abs(left-right)/max(projection['error_energy'],np.finfo(float).tiny)),
                  decomposition_qualified=projection['status']=='PROJECTION_CLOSED',
                  dg_in_range_P=True, dg=dg, q=q)
    identity = copied_apply(prolong,copied_apply(solve,copied_apply(adjoint,copied_apply(action,parallel))))
    result['coarse_identity_relative_field_error'] = float(np.sqrt(metric_square(mass,identity-parallel)/
        max(metric_square(mass,parallel),np.finfo(float).tiny)))
    return result


def evaluate_profiles(action, mass, e, profiles, *, checkpoint=lambda: None):
    """Once per supplied profile, using the same normalized q and e."""
    q = copied_apply(action,e)
    scale = float(np.linalg.norm(q))
    if scale == 0:
        raise ValueError('cannot normalize zero action of diagnostic error')
    e, q = np.array(e,copy=True)/scale, q/scale
    result = {}
    for name, profile in profiles.items():
        checkpoint()
        z = copied_apply(profile,q)
        result[name] = correction_diagnostics(action,mass,e,q,z)
        result[name]['correction'] = z
    return dict(normalization_scale=scale, normalized_q=q,normalized_error=e,profiles=result)


def evaluate_residual_profiles(action, mass, residual, profiles, *, checkpoint=lambda: None):
    """Actual failed-case dual inputs remain useful without a reference field."""
    scale = float(np.linalg.norm(residual))
    if scale == 0 or not np.isfinite(scale):
        raise ValueError('residual must be finite and nonzero')
    q = np.array(residual,copy=True)/scale
    result = {}
    for name, profile in profiles.items():
        checkpoint()
        z = copied_apply(profile,q)
        az = copied_apply(action,z)
        energy=metric_square(mass,z)
        qnorm=float(np.linalg.norm(q));remaining=float(np.linalg.norm(q-az))
        result[name] = dict(true_residual_ratio=remaining/qnorm,q_norm=qnorm,true_residual_norm=remaining,
                            correction_field_energy=energy,correction_field_norm=float(np.sqrt(energy)),
                            remaining_field_error='UNAVAILABLE_NO_REFERENCE', correction=z,applied_direction=az)
    return dict(input_role='dual residual', normalization_scale=scale,normalized_q=q,profiles=result)


def homogeneity_check(q, corrections, profiles, *, scale=2., checkpoint=lambda: None):
    """One predeclared rescaling; compare with already saved base corrections."""
    result={}
    for name,profile in profiles.items():
        checkpoint()
        repeated=copied_apply(profile,scale*np.asarray(q))
        expected=scale*corrections[name]
        result[name]=dict(relative_error=float(np.linalg.norm(repeated-expected)/max(np.linalg.norm(expected),np.finfo(float).tiny)),
                          input_scale=scale,scaled_correction=repeated)
    return result
