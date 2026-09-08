"""Opt-in, bounded call-tree timing for the existing physical PC objects."""

from contextlib import contextmanager
from functools import wraps
import time


class PCTiming:
    """Aggregate nested scopes; borrowed results and exceptions pass unchanged."""

    def __init__(self, clock=time.perf_counter):
        self.clock = clock
        self.rows = {}
        self.stack = []
        self.restores = []

    @contextmanager
    def scope(self, name):
        path = tuple(frame[0] for frame in self.stack) + (name,)
        frame = [name, self.clock(), 0.0]
        self.stack.append(frame)
        failed = False
        try:
            yield
        except BaseException:
            failed = True
            raise
        finally:
            elapsed = self.clock() - frame[1]
            self.stack.pop()
            if self.stack:
                self.stack[-1][2] += elapsed
            row = self.rows.setdefault('/'.join(path), dict(
                calls=0, failures=0, inclusive_seconds=0.0, exclusive_seconds=0.0))
            row['calls'] += 1
            row['failures'] += int(failed)
            row['inclusive_seconds'] += elapsed
            row['exclusive_seconds'] += elapsed-frame[2]

    def replace(self, owner, name, value):
        # Restore inherited methods by deleting the temporary instance override.
        present = name in vars(owner)
        previous = getattr(owner, name)
        self.restores.append((owner, name, present, previous))
        setattr(owner, name, value)

    def wrap(self, owner, name, label, after=None):
        original = getattr(owner, name)

        @wraps(original)
        def measured(*args, **kwargs):
            with self.scope(label):
                result = original(*args, **kwargs)
            if after is not None:
                after(args, result)
            return result

        self.replace(owner, name, measured)

    def close(self):
        for owner, name, present, previous in reversed(self.restores):
            if present:
                setattr(owner, name, previous)
            else:
                delattr(owner, name)
        self.restores.clear()

    def snapshot(self):
        return {key: dict(value) for key, value in sorted(self.rows.items())}


class _TimedMatrix:
    """Borrow a PETSc matrix; intercept only mult and forward everything else."""

    def __init__(self, matrix, timing, label):
        self.matrix, self.timing, self.label = matrix, timing, label

    def mult(self, *args):
        with self.timing.scope(self.label):
            return self.matrix.mult(*args)

    def __getattr__(self, name):
        return getattr(self.matrix, name)


class _TimedMPC:
    """Borrow the slotted MPC; intercept B6 calls without modifying shared state."""

    def __init__(self, mpc, timing):
        self.mpc, self.timing = mpc, timing

    def homogenize(self, *args, **kwargs):
        with self.timing.scope('MPC.homogenize'):
            return self.mpc.homogenize(*args, **kwargs)

    def backsubstitution(self, *args, **kwargs):
        with self.timing.scope('MPC.backsubstitution'):
            return self.mpc.backsubstitution(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.mpc, name)


def instrument_reference_pc(bundle, timing, capture):
    """Install after setup; restore before any solver destruction. No new inverse."""
    from . import fullspace_physical_intermediate as core

    positive = bundle['positive']
    upper, lower = positive['upper_cycle'], positive['lower_cycle']
    b6 = positive['p6_shell'].action
    timing.wrap(b6, 'apply', 'B6')
    if getattr(b6, '_local_kernel', None) is None:
        timing.wrap(b6, '_pack_coefficients', 'pack')
        timing.wrap(b6, '_assemble_vector', 'assemble')
    else:
        timing.wrap(b6._local_kernel, 'apply', 'assemble')
    # Only B6's borrowed reference changes. A6 and the slotted MPC stay intact.
    timing.replace(b6, '_mpc', _TimedMPC(b6._mpc, timing))
    b3 = _TimedMatrix(lower.fine_matrix, timing, 'B3')
    timing.replace(lower, 'fine_matrix', b3)
    timing.replace(lower.smoother, 'matrix', b3)
    timing.replace(lower, 'coarse_matrix', _TimedMatrix(lower.coarse_matrix, timing, 'B1.check'))
    timing.wrap(lower.coarse_solver, 'solve_lean', 'p1.solve')
    timing.wrap(lower, 'apply_into', 'S3')
    timing.wrap(upper, 'apply_into', 'S6', after=lambda args, result: capture('S6', args[1]))
    for transfer, pair in ((upper.p63_transfer, '63'), (lower.owner_transfer, '31')):
        for method, label in (('apply_primal_into', 'P'), ('apply_adjoint_into', 'PH')):
            timing.wrap(transfer, method, label+pair)
    p64 = bundle['actions']['transfers'][(6, 4)]
    timing.wrap(p64, 'apply_primal', 'P64')
    timing.wrap(p64, 'apply_adjoint', 'PH64')
    reference = bundle['reference_factor']
    timing.wrap(reference, 'solve_intermediate', 'A4.solve_check')
    timing.wrap(reference, 'marker', 'log_marker')
    timing.wrap(reference, 'sample', 'resource_sample')
    timing.wrap(reference.factor, 'solve_repeated', 'factor_backsolve')
    timing.wrap(reference.action, 'apply', 'A4.check_action')
    fine = bundle['fine']
    timing.wrap(fine['physical_action'], 'apply', 'A6',
                after=lambda args, result: capture('A6', args[1]))
    timing.wrap(fine['volume_action'], 'apply', 'volume')
    timing.wrap(fine['dtn_action'], 'apply', 'DtN')
    if ('equivalent_fast' in bundle and
            bundle['pc'].fine_action is bundle['equivalent_fast']['physical_action']):
        fast = bundle['equivalent_fast']
        timing.wrap(fast['physical_action'], 'apply', 'A6',
                    after=lambda args, result: capture('A6', args[1]))
        timing.wrap(fast['volume_action'], 'apply', 'volume')
        for name, action in fast['volume_action'].component_actions.items():
            timing.wrap(action._local_kernel, 'apply', name+'_assemble')
    timing.wrap(core, 'modified_residual_accept', 'MR')
    timing.wrap(bundle['pc'], 'stage_callback', 'log_marker')
    for method in ('_norm', '_dot', '_axpy', '_scale', '_copy', '_new_like', '_destroy'):
        timing.wrap(core, method, 'Vec.'+method.removeprefix('_'))
