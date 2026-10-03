"""Fixed unit-coefficient direct-outer-input correction, not a solver or fit."""
import numpy as np
from src.solvers.return_block_direction import OUTER_BLOCKS, NAMES

FAMILY = 'FIXED_FULL_INPUT_BLOCK_CORRECTION_DIAGNOSTIC'
CAPS = dict(actions=32, factor_readers=1, outer_lu_solve=0, joint_lu_solve=4,
    explicit_triangular_pass=8, thin_decompositions=0, port_factors=1,
    port_solves=32, port_rhs_columns=32, new_assemblies=0, new_LU_attempts=0,
    new_gecon=0)
EXPECTED = dict(CAPS, actions=22, port_solves=21, port_rhs_columns=21)
VECTOR_KEYS = ('input_residual','u','au_cached','au','k','ak','delta','adelta',
               'qret','aqret_cached','aqret','qfull','aqfull','q0','aq0','qj','aqj',
               'joint_local_image','audited_full_residual','reclosed_port')


def ratio(error, scale):
    return error/scale if scale else (0. if error == 0 else None)


def decision(rows):
    if len(rows) != 2 or {r['name'] for r in rows} != set(NAMES):
        return 'PARTIAL'
    if not all(r.get('trustworthy') is True for r in rows):
        return 'NUMERICALLY_UNRESOLVED'
    if all(r['rho_full'] <= .75 and r['rho0'] > 0 and
           r['rho_full'] <= .8*r['rho0'] for r in rows):
        return 'FULL_INPUT_SINGLE_STEP_SIGNAL'
    if (all(r['rho_full'] >= .95 for r in rows) or
            all(r['rho_full'] >= r['rho0']-1e-10 for r in rows)):
        return 'FULL_INPUT_FIXED_STEP_INSUFFICIENT'
    return 'STATE_DEPENDENT_INCONCLUSIVE'


def support_inventory(directions, images, groups, n):
    """Columns are block corrections, never fitted-coefficient combinations."""
    if (directions.shape != (n,8) or images.shape != (n,8) or
            not np.isfinite(directions).all() or not np.isfinite(images).all()):
        raise ValueError('V25 fixed eight-column cache inventory')
    for b in range(8):
        if np.count_nonzero(directions[groups != b, b]):
            raise ValueError('V25 column/support order mismatch')


def direct_input(directions, images, qj, qret, ids, solve, apply, scale):
    """Six original actions and one J solve; all coefficients exactly +/-1."""
    u = np.sum(directions[:, OUTER_BLOCKS], axis=1)
    au_cached = np.sum(images[:, OUTER_BLOCKS], axis=1)
    scales = {}
    def original(name, value):
        response = apply(value)
        scales[name] = scale(value)
        return response
    au = original('u', u)
    k = np.zeros_like(u); k[ids] = solve(au[ids])
    ak = original('k', k)
    delta = u-k
    adelta = original('delta', delta)
    aqret = original('qret', qret)
    qfull = qret+delta
    aqfull = original('qfull', qfull)
    q0 = qj+u
    aq0 = original('q0', q0)
    return dict(u=u, au_cached=au_cached, au=au, k=k, ak=ak,
                delta=delta, adelta=adelta, qret=qret, aqret=aqret,
                qfull=qfull, aqfull=aqfull, q0=q0, aq0=aq0), scales


def certificates(a, r, ids, *, bn, scales):
    """Save both physical-b and current-r denominators and pre-cancel scales."""
    rn = float(np.linalg.norm(r))
    checks = {}
    def check(name, left, right, op):
        err = float(np.linalg.norm(left-right))
        checks[name] = dict(error_norm=err, operation_scale=float(op),
            full_b_relative=ratio(err,bn), current_r_relative=ratio(err,rn),
            operation_relative=ratio(err,float(op)))
    check('cached_outer_action', a['au'], a['au_cached'], scales['u'])
    check('cached_return_action', a['aqret'], a['aqret_cached'], scales['qret'])
    check('delta_linearity', a['adelta'], a['au']-a['ak'], scales['u']+scales['k'])
    check('full_linearity', a['aqfull'], a['aqret']+a['adelta'], scales['qret']+scales['delta'])
    check('control_linearity', a['aq0'], a['aqj']+a['au'],
          float(np.linalg.norm(a['aqj']))+scales['u'])
    check('J_delta_cancellation', a['adelta'][ids], np.zeros(len(ids)), scales['u']+scales['k'])
    check('J_full_rhs', a['aqfull'][ids], r[ids], scales['qret']+scales['u']+scales['k']+rn)
    # Matrix-times-k and the unaltered solve RHS are saved, so this witness is
    # recheckable without loading the matrix/factor in the cached checker.
    check('J_feedback_solve', a['joint_local_image'], a['au'][ids],
          float(np.linalg.norm(a['joint_local_image'])+np.linalg.norm(a['au'][ids])))
    safe = all(c['full_b_relative'] is not None and c['full_b_relative'] <= 1e-11
               and c['operation_relative'] is not None and c['operation_relative'] <= 1e-10
               for c in checks.values())
    outer = r.copy(); outer[ids] = 0
    on = float(np.linalg.norm(outer))
    metrics = dict(trustworthy=safe, full_b_norm=bn, residual_norm=rn,
        rho_full=ratio(float(np.linalg.norm(r-a['aqfull'])),rn),
        rho0=ratio(float(np.linalg.norm(r-a['aq0'])),rn),
        rho_ret=ratio(float(np.linalg.norm(r-a['aqret'])),rn),
        outer_isolated_ratio=ratio(float(np.linalg.norm(outer-a['adelta'])),on) if on else None,
        outer_isolated_status='MEASURED' if on else 'NOT_APPLICABLE',
        unit_coefficients=True, fitted_coefficients_used=False, checks=checks)
    return metrics
