"""Owned residual bookkeeping for a nonlinear two-call coarse inverse."""
import time
import numpy as np
from .fullspace_physical_intermediate import _copy, _destroy, _norm, _axpy
from .physical_balanced_coupling import BalancedConstraintRejected


def _array(value):
    return np.asarray(value.array if hasattr(value, 'array') else value).copy()


class InexactBalanceLedger:
    def __init__(self, action, restriction, *, save, checkpoint=lambda: None, every=32):
        if every < 1:
            raise ValueError('audit period must be positive')
        self.A, self.PH, self.save = action, restriction, save
        self.checkpoint, self.every = checkpoint, every
        self.calls, self.last = [], None
        self.audit_count = self.A_count = self.PH_count = 0
        self.audit_seconds = 0.

    def begin(self):
        self.abort()
        self._clear_last()

    def record(self, g, applied, residual, facts):
        # A copy is mandatory: the next I4 call may overwrite its work buffer.
        if len(self.calls) >= 2:
            raise ValueError('only two coarse calls per balanced action')
        self.calls.append(dict(eps=_copy(residual), rhs_norm=_norm(g),
            applied_norm=_norm(applied), eps_norm=_norm(residual), inner=dict(facts)))

    def abort(self):
        for item in self.calls:
            _destroy(item['eps'])
        self.calls.clear()

    def _clear_last(self):
        if self.last is not None:
            for key in ('q', 'z', 'difference'):
                _destroy(self.last[key])
            self.last = None

    def finish(self, q, z, iteration):
        if len(self.calls) != 2:
            raise ValueError('missing eps1/eps2 from coarse calls')
        first, second = self.calls
        difference = _copy(first['eps']); _axpy(difference, -1, second['eps'])
        summary = dict(policy='INEXACT_EPS_DIFFERENCE', iteration=iteration,
            calls=[{k:v for k,v in x.items() if k != 'eps'} for x in self.calls],
            difference_norm=_norm(difference),
            operation_scale=sum(x['rhs_norm']+x['applied_norm'] for x in self.calls),
            actual_audit='not_sampled')
        self.last = dict(q=_copy(q), z=_copy(z), difference=difference, summary=summary)
        self.abort()
        if iteration == 1 or iteration % self.every == 0:
            self.audit_last()
        return summary

    def audit_last(self):
        if self.last is None:
            return None
        self.checkpoint()
        started = time.perf_counter()
        az = residual = defect = closure = None
        try:
            self.A_count += 1; az = self.A(self.last['z'])
            residual = _copy(self.last['q']); _axpy(residual, -1, az)
            self.PH_count += 1; defect = self.PH(residual)
            closure = _copy(defect); _axpy(closure, -1, self.last['difference'])
            numerator, defect_norm = _norm(closure), _norm(defect)
            scale = self.last['summary']['operation_scale']
            ratio = numerator/scale if scale else (0. if numerator == 0. else float('inf'))
            row = dict(actual_defect_norm=defect_norm, closure_norm=numerator,
                operation_scale=scale, closure_relative=ratio, closure_limit=1e-8,
                defect_scaled=defect_norm/scale if scale else (0. if defect_norm == 0 else float('inf')))
            if not np.isfinite(ratio) or ratio > 1e-8:
                self.save('inexact_balance_failure', dict(q=_array(self.last['q']), z=_array(self.last['z']),
                    expected_difference=_array(self.last['difference']), actual_defect=_array(defect), **row))
                raise BalancedConstraintRejected(row)
            self.audit_count += 1
            self.last['summary'].update(actual_audit='PASS', audit=row)
            return row
        finally:
            self.audit_seconds += time.perf_counter()-started
            for value in (closure, defect, residual, az):
                if value is not None: _destroy(value)

    def destroy(self):
        self.abort(); self._clear_last()
