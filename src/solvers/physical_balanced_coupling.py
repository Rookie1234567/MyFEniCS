"""Fixed dual/primal balanced actions; no reference field enters this module."""
import time
import numpy as np
from .fullspace_physical_intermediate import _copy, _destroy, _norm, _dot, _axpy, _scale, _zero

ROUTES = ('BAL_H', 'BAL_S', 'PROJ_K6')


class BalancedNumericalRejected(RuntimeError):
    def __init__(self, facts):
        self.facts = facts
        super().__init__(type(self).__name__+': '+str(facts))


class BalancedConstraintRejected(BalancedNumericalRejected):
    pass


class BalancedArnoldiRejected(BalancedNumericalRejected):
    pass


class _OwnedVectors:
    """Own only new fine vectors, including outputs from owned callbacks."""
    def __init__(self):
        self.values = {}
        self.peak = 0

    def take(self, value):
        if id(value) in self.values:
            raise TypeError('callback returned a live borrowed vector')
        self.values[id(value)] = value
        self.peak = max(self.peak, len(self.values))
        if self.peak > 32:
            raise RuntimeError('balanced fine-vector live-set exceeds 32')
        _norm(value)
        return value

    def copy(self, value):
        return self.take(_copy(value))

    def release(self, value):
        return self.values.pop(id(value))

    def drop(self, value):
        _destroy(self.release(value))

    def close(self):
        for value in list(self.values.values()):
            self.drop(value)


class PhysicalBalancedCoupling:
    """C: dual->primal, A: primal->dual, smoother: dual->primal.

    All callbacks return caller-owned vectors. Adapt borrowed FE buffers using
    the existing apply_owned/BorrowedActionAdapter before construction.
    Restriction is P^H on duals and returns an owned coarse vector.
    """
    def __init__(self, action, coarse, smoother, restriction, *, route, checkpoint=lambda: None,
                 inexact_ledger=None, level_identity=None, capture_vectors=False):
        if route not in ROUTES and route != 'ONE_C':
            raise ValueError('unknown balanced route')
        self.A, self.C, self.S, self.PH = action, coarse, smoother, restriction
        self.route, self.checkpoint = route, checkpoint
        self.apply_count = self.attempted = 0
        self.total_counts = dict(C=0, smoother=0, A_structure=0, A_inner_true=0,
                                 PH_audit=0)
        self.total_operation_seconds = dict(C=0.0, smoother=0.0,
                                            A_structure=0.0, A_inner_true=0.0)
        self.last_apply_facts = {}
        self.capture_vectors = bool(capture_vectors)
        self.last_apply_vectors = {}
        if inexact_ledger is not None and route == 'BAL_H':
            if getattr(inexact_ledger, 'mode', 'BAL_H') != 'BAL_H':
                raise ValueError('BAL_H requires a BAL_H inexact ledger')
        elif inexact_ledger is not None and route == 'ONE_C':
            if getattr(inexact_ledger, 'mode', None) != 'ONE_C':
                raise ValueError('ONE_C requires a ONE_C inexact ledger')
        elif inexact_ledger is not None:
            raise ValueError('inexact ledger is qualified only for BAL_H or explicit ONE_C')
        if route == 'ONE_C' and inexact_ledger is None:
            raise ValueError('ONE_C requires an explicit inexact-balance ledger')
        self.inexact_ledger, self.level_identity = inexact_ledger, level_identity

    def apply(self, source):
        vectors = _OwnedVectors()
        self.attempted += 1
        counts = dict(C=0, smoother=0, A_structure=0, A_inner_true=0, PH_audit=0)
        operation_seconds = dict(C=0.0, smoother=0.0, A_structure=0.0, A_inner_true=0.0)
        facts = dict(route=self.route, status='STARTED', counts=counts, inner=[],
                     operation_seconds=operation_seconds,
                     projection_space='ker(PH A), not M0-orthogonal complement',
                     vector_scope='new fine vectors only; coarse solver/smoother/outer storage separate')
        self.last_apply_facts = facts
        self.last_apply_vectors = {}
        if self.level_identity is not None:
            facts['level_identity'] = self.level_identity
        if self.inexact_ledger is not None:
            self.inexact_ledger.begin()
            identity = 'eps1-eps2' if self.route == 'BAL_H' else 'eps1-g2'
            facts['projection_space'] = f'inexact coarse balance, {identity}; not exact projection'

        def call(name, function, x):
            self.checkpoint()
            counts[name] += 1
            started = time.perf_counter()
            try:
                value = function(x)
            finally:
                operation_seconds[name] += time.perf_counter() - started
            if value is source or value is x:
                raise TypeError('balanced callback must return caller-owned output')
            return vectors.take(value)

        def balance(residual, leading):
            # residual=leading-other; scale by actual participating coarse terms.
            counts['PH_audit'] += 2
            left = self.PH(leading)
            try:
                defect = self.PH(residual)
                try:
                    numerator = _norm(defect)
                    scale = _norm(left)
                    _axpy(left, -1, defect)
                    scale += _norm(left)
                    relative = numerator/max(scale, np.finfo(float).tiny)
                    if not np.isfinite(relative) or relative > 1e-8:
                        raise BalancedConstraintRejected(dict(norm=numerator,operation_scale=scale,
                            relative=relative,limit=1e-8))
                    return dict(norm=numerator, operation_scale=scale, relative=relative, limit=1e-8)
                finally:
                    _destroy(defect)
            finally:
                _destroy(left)

        try:
            _norm(source)
            zc = call('C', self.C, source)
            u = call('A_structure', self.A, zc)
            rc = vectors.copy(source); _axpy(rc, -1, u)
            if self.inexact_ledger is not None:
                initial_constraint = {'policy': 'inexact_eps1_not_required_zero'}
            elif self.route == 'ONE_C':
                initial_constraint = {'policy': 'one_c_eps1_not_required_zero'}
            else:
                initial_constraint = balance(rc, source)
            facts['initial'] = dict(q_norm=_norm(source), zc_norm=_norm(zc), Azc_norm=_norm(u),
                                    rc_norm=_norm(rc), constraint=initial_constraint)
            vectors.drop(u)
            if self.route != 'PROJ_K6':
                s = v = t = None
                s = call('smoother', self.S, rc)
                v = call('A_structure', self.A, s)
                if self.route == 'ONE_C':
                    # ONE_C deliberately omits the second coarse correction:
                    # z=zc+s.  Its correctness is the operation-relative
                    # eps1-g2 identity, audited with the same PH map.
                    facts['feedback'] = {'s_norm': _norm(s), 'As_norm': _norm(v)}
                    g2 = self.PH(v)
                    vectors.take(g2)
                    self.inexact_ledger.record_g2(g2)
                    vectors.drop(g2)
                    z = vectors.copy(zc)
                    _axpy(z, 1, s)
                    facts['feedback']['after_field_norm'] = _norm(z)
                else:
                    t = call('C', self.C, v)
                    facts['feedback'] = dict(s_norm=_norm(s), As_norm=_norm(v), feedback_norm=_norm(t))
                    before = vectors.copy(rc); _axpy(before, -1, v)
                    facts['feedback']['before_residual_norm'] = _norm(before)
                    vectors.drop(before)
                    z = vectors.copy(zc); _axpy(z, 1, s)
                    facts['feedback']['before_field_norm'] = _norm(z)
                    _axpy(z, -1, t)
                    facts['feedback']['after_field_norm'] = _norm(z)
                facts['status'] = 'BALANCED_ACTION_COMPLETED'
            else:
                beta = _norm(rc)
                delta = vectors.copy(rc); _zero(delta)
                facts['status'] = 'INNER_ZERO_RESIDUAL' if beta == 0 else 'INNER_TARGET_NOT_REACHED'
                if beta:
                    basis = [vectors.copy(rc)]; _scale(basis[0], 1/beta)
                    directions = []
                    H = np.zeros((7, 6), dtype=np.complex128)
                    for j in range(6):
                        h = call('smoother', self.S, basis[j])
                        ah = call('A_structure', self.A, h)
                        t = call('C', self.C, ah)
                        zj = vectors.copy(h); _axpy(zj, -1, t)
                        directions.append(zj)
                        w = call('A_structure', self.A, zj)
                        constraint = balance(w, ah)
                        before = _norm(w)
                        vectors.drop(h); vectors.drop(ah); vectors.drop(t)
                        # Two-pass modified Gram-Schmidt, complex Hermitian dot.
                        for _ in range(2):
                            for i, vi in enumerate(basis):
                                coefficient = _dot(vi, w)
                                H[i, j] += coefficient
                                _axpy(w, -coefficient, vi)
                        next_norm = _norm(w); H[j+1, j] = next_norm
                        small_rhs = np.zeros(j+2, dtype=np.complex128); small_rhs[0] = beta
                        try:
                            y, _, rank, singular = np.linalg.lstsq(H[:j+2, :j+1], small_rhs, rcond=None)
                        except np.linalg.LinAlgError as exc:
                            raise BalancedArnoldiRejected(dict(iteration=j+1,
                                hessenberg=H[:j+2, :j+1].copy(),reason=str(exc))) from exc
                        if not np.isfinite(y).all():
                            raise BalancedArnoldiRejected(dict(iteration=j+1,
                                hessenberg=H[:j+2, :j+1].copy(),reason='nonfinite least-squares coefficients'))
                        _zero(delta)
                        for direction, coefficient in zip(directions, y):
                            _axpy(delta, coefficient, direction)
                        adelta = call('A_inner_true', self.A, delta)
                        actual = vectors.copy(rc); _axpy(actual, -1, adelta)
                        relative = _norm(actual)/beta
                        vectors.drop(actual); vectors.drop(adelta)
                        saturated = next_norm <= 64*np.finfo(float).eps*before
                        facts['inner'].append(dict(iteration=j+1, true_relative=relative,
                            constraint=constraint, rank=int(rank), singular_values=singular.tolist(),
                            saturated=bool(saturated), hessenberg=H[:j+2, :j+1].copy(), coefficients=y.copy()))
                        if relative <= .25:
                            facts['status'] = 'INNER_TARGET_REACHED'
                            vectors.drop(w); break
                        if saturated:
                            facts['status'] = 'INNER_TARGET_NOT_REACHED'
                            facts['saturation_without_target'] = True
                            vectors.drop(w); break
                        if j < 5:
                            _scale(w, 1/next_norm); basis.append(w)
                        else:
                            vectors.drop(w)
                z = vectors.copy(zc); _axpy(z, 1, delta)
            _norm(z)
            if self.capture_vectors:
                self.last_apply_vectors = dict(
                    q=np.array(source.array, copy=True),
                    zc=np.array(zc.array, copy=True),
                    rc=np.array(rc.array, copy=True),
                    s=np.array(s.array, copy=True) if s is not None else None,
                    A6s=np.array(v.array, copy=True) if v is not None else None,
                    c2=np.array(t.array, copy=True) if t is not None else None,
                    z=np.array(z.array, copy=True),
                )
            if self.inexact_ledger is not None:
                facts['inexact_balance'] = self.inexact_ledger.finish(source, z, self.attempted)
            self.apply_count += 1
            facts['apply_count'] = self.apply_count
            return vectors.release(z)
        except BaseException as exc:
            facts.update(status='ACTION_FAILED', exception_type=type(exc).__name__, exception=str(exc))
            if self.inexact_ledger is not None:
                self.inexact_ledger.abort()
            raise
        finally:
            for name, count in counts.items():
                self.total_counts[name] += int(count)
            for name, elapsed in operation_seconds.items():
                self.total_operation_seconds[name] += float(elapsed)
            facts['peak_new_fine_vectors'] = vectors.peak
            facts['live_before_cleanup'] = len(vectors.values)
            vectors.close()
            facts['live_after_cleanup'] = len(vectors.values)
