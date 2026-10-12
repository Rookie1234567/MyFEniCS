"""Opt-in exact Jacobi and three-direction nonlinear residual minimization.

No reference field enters these operations. Small least squares is solved
directly on the three image columns, never by normal equations.
"""
import time

import numpy as np
from scipy import linalg


def pullback_diagonal(S, E):
    """diag(E^H S E), including non-injective and multi-entry MPC rows."""
    SE = S @ E
    coo = E.tocoo()
    result = np.zeros(E.shape[1], np.complex128)
    np.add.at(result, coo.col, np.conj(coo.data) * SE[coo.row, coo.col])
    return result


def trace_diagonal(service, left, right):
    service.require_frozen()
    result = np.zeros(service.nt + service.m, np.complex128)
    for index, (_, _, ids, E, key) in enumerate(service.cell_records):
        S = service.cache[key]['schur']
        single = service.single_maps[index]
        if single is not None and len(np.unique(single[0])) == len(single[0]):
            rows, coefficients = single
            np.add.at(result, rows, np.conj(coefficients) * np.diag(S) * coefficients)
        else:
            np.add.at(result, ids, pullback_diagonal(S, E))
    result[service.nt:] = np.diag(service.Htilde)
    with np.errstate(invalid='ignore', over='ignore'):
        result *= left * right
    if not np.isfinite(result).all():
        raise FloatingPointError('nonfinite physical complex diagonal')
    inverse = np.ones_like(result)
    nonzero = result != 0
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        inverse[nonzero] = 1 / result[nonzero]
    if not np.isfinite(inverse).all():
        raise FloatingPointError('overflow in unshifted complex Jacobi')
    return result, inverse, int(np.count_nonzero(~nonzero))


def effect_gate(iteration, original_true, retained_true):
    rho = max(float(original_true), float(retained_true))
    limit = {32: .5, 64: .1, 128: 1e-3}.get(int(iteration))
    return dict(iteration=int(iteration), rho=rho, limit=limit,
                evaluated=limit is not None,
                pass_gate=limit is None or np.isfinite(rho) and rho <= limit)


def least_residual_weights(v, W, *, driver='gelsd'):
    """Preserve zero, optimal single columns and the original fixed sum."""
    norms = np.linalg.norm(W, axis=0)
    scales = np.where(norms == 0, 1., norms)
    normalized = W / scales
    coefficients, _, rank, singular = linalg.lstsq(
        normalized, v, cond=1e-12, lapack_driver=driver, check_finite=True)
    candidates = [('LS', coefficients / scales), ('ZERO', np.zeros(3, complex)),
                  ('FIXED_COARSE_PLUS_LOCAL', np.array([0, 1, 1], complex))]
    for j, name in enumerate(('IDENTITY', 'COARSE', 'LOCAL')):
        weight = np.zeros(3, complex)
        if norms[j] > 0:
            # Normalizing the one-column projection avoids squaring its scale.
            col = normalized[:, j]
            weight[j] = np.vdot(col, v) / np.vdot(col, col) / scales[j]
        candidates.append(('BEST_SINGLE_' + name, weight))
    scores = []
    for name, weight in candidates:
        residual = v - W @ weight
        norm = float(np.linalg.norm(residual))
        if np.isfinite(norm) and np.isfinite(weight).all():
            scores.append((norm, name, weight))
    if not scores:
        raise FloatingPointError('no finite residual candidate')
    best = min(scores, key=lambda row: row[0])
    facts = dict(column_norms=norms.tolist(), column_scales=scales.tolist(),
        rank=int(rank), rcond=1e-12, singular_values=None if singular is None else singular.tolist(),
        candidates=[dict(name=n, residual_norm=r) for r, n, _ in scores],
        selected=best[1], predicted_residual_norm=best[0],
        weights_real=best[2].real.tolist(), weights_imag=best[2].imag.tolist(),
        driver=driver)
    return best[2], facts


class ResidualMinimizedPC:
    """Three input-dependent complex weights; deliberately not additive."""
    def __init__(self, base, action, append=lambda row: None, witness=lambda *args: None):
        self.base, self.action, self.append = base, action, append
        self.witness = witness
        self.calls = base.calls
        self.calls.update(SMR_original_action=0, SMR_zero=0, SMR_retry=0)
        self.seconds = base.seconds
        self.seconds.update(small_LS=0., SMR_original=0.)

    def apply_original(self, v):
        self.calls['SMR_original_action'] += 1
        began = time.perf_counter()
        try:
            return self.action(v)
        finally:
            self.seconds['SMR_original'] += time.perf_counter()-began

    def __call__(self, v):
        self.calls['apply'] += 1
        norm = float(np.linalg.norm(v))
        if norm == 0:
            self.calls['SMR_zero'] += 1
            self.append(dict(call=self.calls['apply'], zero=True))
            return np.zeros_like(v)
        dc = self.base.coarse_apply(v)
        ac = self.apply_original(dc)
        dl = self.base.local_apply(v - ac)
        D = np.column_stack((v, dc, dl))
        W = np.column_stack((self.apply_original(v), ac, self.apply_original(dl)))
        # D/W, normalized W and LAPACK buffers stay bounded, not a column bank.
        if 6 * W.nbytes + 8 * v.nbytes > 512 * 2**20:
            raise MemoryError('three-column workspace exceeds512MiB')
        began = time.perf_counter()
        weights, facts = least_residual_weights(v, W)
        self.seconds['small_LS'] += time.perf_counter() - began
        z = D @ weights
        predicted = W @ weights
        actual = self.apply_original(z) if np.any(z) else np.zeros_like(v)
        scale = max(norm + np.linalg.norm(predicted) + np.linalg.norm(actual), 1e-300)
        defect = float(np.linalg.norm(actual - predicted) / scale)
        if defect > 1e-10:
            self.calls['SMR_retry'] += 1
            weights, facts = least_residual_weights(v, W, driver='gelsy')
            z = D @ weights
            predicted = W @ weights
            actual = self.apply_original(z) if np.any(z) else np.zeros_like(v)
            scale = max(norm + np.linalg.norm(predicted) + np.linalg.norm(actual), 1e-300)
            defect = float(np.linalg.norm(actual - predicted) / scale)
        actual_norm = float(np.linalg.norm(v - actual))
        protected = min(row['residual_norm'] for row in facts['candidates'])
        valid = (np.isfinite(z).all() and defect <= 1e-10
                 and actual_norm <= protected + 1e-10 * scale)
        self.append(dict(facts, call=self.calls['apply'], rhs_norm=norm,
            actual_residual_norm=actual_norm, actual_relative=actual_norm / norm,
            operation_scaled_defect=defect, numerical_protection_pass=bool(valid),
            workspace_bound_bytes=6 * W.nbytes + 8 * v.nbytes,
            nonlinear_input_dependent_weights=True, reference_reads=0))
        if not valid:
            raise ValueError('SMR original-action residual protection failed')
        if self.calls['apply'] <= 2:
            self.witness(self.calls['apply'], v, D, W, z)
        return z

    def destroy(self):
        self.base.destroy()
