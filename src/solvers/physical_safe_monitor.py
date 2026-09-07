"""Solution-only safe snapshots without changing the active Arnoldi cycle."""
import time

import numpy as np


def conservative_stagnation(cycles):
    if len(cycles) < 5 or cycles[-1]['end_iteration'] < 256:
        return False
    for previous, current in zip(cycles[-5:-1], cycles[-4:]):
        old, new = previous['explicit_true_residual'], current['explicit_true_residual']
        if (current['iterations'] != 32 or current['end_iteration']-current['start_iteration'] != 32
                or previous['end_iteration'] != current['start_iteration']
                or not np.isfinite([old, new]).all() or old <= 0 or new/old < .99):
            return False
    return True


class PhysicalSafeMonitor:
    def __init__(self, rhs, apply_action, checkpoint, append, stop_requested, *, clock=time.monotonic):
        self.rhs, self.apply_action = rhs, apply_action
        self.checkpoint, self.append, self.stop_requested = checkpoint, append, stop_requested
        self.clock = clock
        self.target = rhs.duplicate()
        self.last_saved_iteration = 0
        self.last_saved_time = clock()
        self.last_reported_iteration = -1
        self.action_count = 0

    def __call__(self, iteration, reported, ksp, solution, counts):
        reason = int(ksp.getConvergedReason())
        terminal = reason != 0
        if iteration > self.last_reported_iteration:
            self.append('iterations.jsonl', dict(iteration=iteration, reported_norm=reported,
                reported_relative=reported/max(self.rhs.norm(), np.finfo(float).tiny), terminal=terminal, reason=reason,
                monitor_original_A6_action_count=self.action_count, **counts))
            self.last_reported_iteration = iteration
        stop = self.stop_requested()
        due = iteration % 8 == 0 or self.clock()-self.last_saved_time >= 120 or stop
        if due and iteration > self.last_saved_iteration:
            # Terminal FGMRES has already written back vec_sol. Rebuilding it
            # then can add the correction twice. Intermediate buildSolution
            # already includes the nonzero cycle initial guess exactly once.
            if terminal:
                solution.copy(self.target)
            else:
                ksp.buildSolution(self.target)
            action = self.apply_action(self.target)
            residual = self.rhs.copy()
            try:
                residual.axpy(-1, action)
                relative = float(residual.norm()/max(self.rhs.norm(), np.finfo(float).tiny))
                if not np.isfinite(relative):
                    raise FloatingPointError('nonfinite safe original A6 residual')
                self.action_count += 1
                self.checkpoint(iteration, self.target, relative)
                self.append('monitor_residuals.jsonl', dict(iteration=iteration,
                    explicit_true_residual=relative, monitor_action_count=self.action_count, reason=reason,
                    solution_source='terminal_vec_sol' if terminal else 'intermediate_buildSolution'))
                self.last_saved_iteration, self.last_saved_time = iteration, self.clock()
            finally:
                residual.destroy()
                action.destroy()
        if stop:
            raise InterruptedError('performance stop after last safe solution snapshot')

    def destroy(self):
        if self.target is not None:
            self.target.destroy()
            self.target = None
