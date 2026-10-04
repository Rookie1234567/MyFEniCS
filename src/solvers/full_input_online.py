"""Fixed full-space J/O block elimination for arbitrary complex trace RHS.

No cached directions, fitted coefficients, reference field or changing inner
iteration participates in this operator. The original action stays separate.
"""
from time import perf_counter

import numpy as np


FAMILY = 'FIXED_SEVEN_REGION_FULL_INPUT_RIGHT_GMRES256'


class FullInputPC:
    def __init__(self, n, joint, outers, action, *, count=lambda *args: None):
        self.n, self.joint, self.outers = n, joint, tuple(outers)
        self.action, self.count = action, count
        rows = np.concatenate([joint.rows, *(b.rows for b in self.outers)])
        if not np.array_equal(np.sort(rows), np.arange(n)):
            raise ValueError('joint and outer canonical rows must cover exactly once')
        self.calls = self.zero_calls = 0
        self.seconds = 0.

    def __call__(self, r):
        r = np.asarray(r, dtype=np.complex128)
        if r.shape != (self.n,) or not np.isfinite(r).all():
            raise ValueError('finite full trace RHS required')
        self.count('pc_apply')
        began = perf_counter()
        self.calls += 1
        try:
            if not np.count_nonzero(r):
                self.zero_calls += 1
                return np.zeros_like(r)
            q = np.zeros_like(r)
            q[self.joint.rows] = self.joint.solve(r[self.joint.rows])
            remainder = r - self.action(q)
            v = np.zeros_like(r)
            for block in self.outers:
                v[block.rows] = block.solve(remainder[block.rows])
            av = self.action(v)
            result = q + v
            result[self.joint.rows] -= self.joint.solve(av[self.joint.rows])
            if not np.isfinite(result).all():
                raise ValueError('nonfinite fixed block correction')
            return result
        finally:
            self.seconds += perf_counter() - began


def continue_after_cycle(audit, cycle):
    """Original full-b Schur gate; no reference or callback-driven selection."""
    rho = audit['schur_relative']
    if not np.isfinite(rho):
        return False, 'ONLINE_BLOCK_PC_PROGRESS_INSUFFICIENT'
    from src.runners.autonomous_neural_head import original_gate
    passed = original_gate(audit)['status'] == 'ORIGINAL_EQUATION_PASS'
    if passed and rho <= 1e-8:
        return False, 'ORIGINAL_EQUATION_PASS'
    if cycle == 1 and rho <= 1e-2:
        return True, 'SECOND_CYCLE_ADMITTED'
    return False, ('ORIGINAL_EQUATION_PASS' if passed else
                   'ONLINE_BLOCK_PC_PROGRESS_INSUFFICIENT' if cycle == 1 else
                   'ONLINE_BLOCK_PC_NOT_QUALIFIED')
