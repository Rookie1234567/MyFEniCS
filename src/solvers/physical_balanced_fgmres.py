"""One live right-FGMRES32 solve with the frozen V5 investment screen."""
import numpy as np


class BalancedScreen:
    def __init__(self):
        self.checkpoints = []
        self.decision = None

    def inspect(self, iteration, relative, seconds):
        if iteration > 0 and iteration % 32 == 0:
            if not self.checkpoints or self.checkpoints[-1][0] != iteration:
                self.checkpoints.append((iteration, relative))
                self.checkpoints = self.checkpoints[-3:]
        if self.decision is not None or (iteration < 128 and seconds < 1800):
            return self.decision
        history = self.checkpoints
        trend = (len(history) == 3 and history[1][0]-history[0][0] == 32 and
                 history[2][0]-history[1][0] == 32 and
                 0 < history[2][1] < history[1][1] < history[0][1] and
                 np.sqrt(history[2][1]/history[0][1]) <= .65)
        passed = relative <= 1e-2 or trend
        self.decision = dict(status='SCREEN_CONTINUE_SAME_LIVE_KSP' if passed else
            'SCREEN_BUDGET_NO_QUALIFIED_PROGRESS', passed=bool(passed), iteration=iteration,
            true_relative=relative, solve_seconds=seconds, checkpoints=list(history))
        return self.decision


class BoundedScreen:
    """The V7 three-node investment screen for the live outer KSP.

    V7 observes every completed group of eight outer steps, but only saves a
    solution-only checkpoint at a 32-step boundary (or at final exit).  The
    screen is deliberately kept separate from the historical V5 policy so the
    old ``.65``/7200-second behaviour cannot leak into a bounded profile.
    """

    def __init__(self):
        self.checkpoints = []
        self.decision = None
        self.mid_budget_checked = False
        self.mid_budget = None

    def inspect(self, iteration, relative, seconds):
        if iteration == 0 or iteration % 8 == 0:
            if not self.checkpoints or self.checkpoints[-1][0] != iteration:
                self.checkpoints.append((iteration, relative))
                self.checkpoints = self.checkpoints[-3:]
        if self.decision is not None:
            return self.decision
        if iteration < 128 and seconds < 1800:
            return None
        history = self.checkpoints
        trend = (len(history) == 3 and
                 history[1][0] - history[0][0] == 8 and
                 history[2][0] - history[1][0] == 8 and
                 0 < history[2][1] < history[1][1] < history[0][1] and
                 np.sqrt(history[2][1] / history[0][1]) <= .80)
        passed = relative <= 1e-2 or (
            iteration >= 16 and relative <= .30 and trend)
        self.decision = dict(
            status='SCREEN_CONTINUE_SAME_LIVE_KSP' if passed else 'NORMAL_SCREEN_STOP',
            passed=bool(passed), iteration=iteration, true_relative=relative,
            solve_seconds=seconds, checkpoints=list(history), policy='v7',
        )
        return self.decision

    def inspect_mid_budget(self, iteration, relative, seconds):
        """Apply the one-time 5400-second continuation gate."""
        if not self.mid_budget_checked and seconds >= 5400:
            self.mid_budget_checked = True
            self.mid_budget = dict(
                status='MID_BUDGET_CONTINUE' if relative <= 1e-3
                else 'PROGRESS_INSUFFICIENT_AT_MID_BUDGET',
                passed=bool(relative <= 1e-3), iteration=iteration,
                true_relative=relative, solve_seconds=seconds,
            )
        return self.mid_budget


class V9BoundedScreen(BoundedScreen):
    """V9 absolute-progress screen for the equal-new-work profile.

    The eight-step observations are retained for evidence, but iteration 128
    alone never opens the decision.  The first investment decision is made at
    the first safe residual check at or after 1800 seconds and accepts only
    an absolute true residual of at most 0.10.
    """

    def inspect(self, iteration, relative, seconds):
        if iteration == 0 or iteration % 8 == 0:
            if not self.checkpoints or self.checkpoints[-1][0] != iteration:
                self.checkpoints.append((iteration, relative))
                self.checkpoints = self.checkpoints[-3:]
        if self.decision is not None or seconds < 1800:
            return self.decision
        passed = bool(relative <= 0.10)
        self.decision = dict(
            status='SCREEN_CONTINUE_SAME_LIVE_KSP' if passed
            else 'TIME_PROGRESS_SCREEN_STOP',
            passed=passed, iteration=iteration, true_relative=relative,
            solve_seconds=seconds, checkpoints=list(self.checkpoints),
            policy='v9_equal_new_work',
        )
        return self.decision


def run_balanced_fgmres(rhs, action, pc, *, checkpoint, append, seconds,
                       resource_sample=lambda: None, stop_requested=lambda: False,
                       screen_enabled=True, solve_limit_seconds=7200,
                       v7_policy=False, v9_policy=False):
    """Callbacks own action/PC outputs; seconds is a conservative shared clock.

    Exactly one KSP creation and one solve, max2048/restart32/zero start.
    Convergence is decided by explicit true residuals from buildSolution while
    KSP is active. Once solve returns, use vec_sol directly, never build again.
    """
    if not np.isfinite(solve_limit_seconds) or solve_limit_seconds <= 0:
        raise ValueError('positive finite solve limit required')
    if v7_policy and v9_policy:
        raise ValueError('V7 and V9 bounded screen policies are mutually exclusive')
    bounded_policy = bool(v7_policy or v9_policy)
    if bounded_policy and float(solve_limit_seconds) != 10800.0:
        raise ValueError('bounded outer solve limit must be 10800 seconds')
    from petsc4py import PETSc
    from .fullspace_memory_first_krylov import _ActionContext, _PCContext
    from .fullspace_physical_intermediate import _destroy
    ac, pc_context = _ActionContext(action), _PCContext(pc)
    sizes = (rhs.getLocalSize(), rhs.getSize())
    operator = PETSc.Mat().createPython((sizes, sizes), context=ac, comm=rhs.getComm())
    ksp = solution = target = None
    screen = (V9BoundedScreen() if v9_policy else
              BoundedScreen() if v7_policy else BalancedScreen())
    snapshots = []
    explicit_count = 0
    last_save = -120.
    stop_status = None
    last_checkpoint_iteration = -1
    result = None
    norm_rhs = max(float(rhs.norm()), np.finfo(float).tiny)
    if bounded_policy and screen_enabled:
        # Seed the two eight-step ratios with the true initial residual.  The
        # value is normalized by the same RHS norm used by every later node.
        screen.inspect(0, 1.0, seconds())

    def snapshot(iteration, current, reported, *, terminal=False):
        nonlocal explicit_count, last_save, last_checkpoint_iteration
        if current is None:
            solution.copy(target)
        elif iteration == 0:
            target.set(0)
        else:
            current.buildSolution(target)
        av = action(target); residual = rhs.copy()
        try:
            residual.axpy(-1, av)
            relative = float(residual.norm()/norm_rhs)
            if not np.isfinite(relative):
                raise FloatingPointError('nonfinite live FGMRES true residual')
            explicit_count += 1
            checkpoint_due = (not bounded_policy or terminal or iteration == 0 or
                              iteration % 32 == 0)
            if checkpoint_due and iteration != last_checkpoint_iteration:
                checkpoint(iteration, target, relative)
                last_checkpoint_iteration = iteration
            now = seconds(); last_save = now
            row = dict(iteration=iteration, explicit_true_residual=relative,
                       reported_relative=float(reported)/norm_rhs, solve_seconds=now,
                       solution_source='terminal_vec_sol' if current is None else 'live_buildSolution')
            snapshots.append(row); append('monitor_residuals.jsonl', row)
            return relative, now
        finally:
            residual.destroy(); av.destroy()

    try:
        operator.setUp(); solution = operator.createVecRight(); solution.set(0)
        target = solution.duplicate()
        ksp = PETSc.KSP().create(rhs.getComm()); ksp.setOperators(operator)
        ksp.setType('fgmres'); ksp.setGMRESRestart(32); ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED); ksp.setInitialGuessNonzero(False)
        ksp.setTolerances(rtol=0., atol=0., max_it=2048)
        ksp.getPC().setType(PETSc.PC.Type.PYTHON); ksp.getPC().setPythonContext(pc_context)

        def convergence(current, iteration, reported):
            nonlocal stop_status
            iteration = int(iteration); now = seconds(); resource_sample()
            append('iterations.jsonl', dict(iteration=iteration, reported_relative=float(reported)/norm_rhs,
                outer_matvec_count=ac.matvec_count, outer_pc_count=pc_context.apply_count))
            stop = stop_requested() or now >= solve_limit_seconds
            boundary = screen_enabled and screen.decision is None and (
                now >= 1800 or (iteration >= 128 and not v9_policy))
            mid_boundary = (bounded_policy and not screen.mid_budget_checked and
                            now >= 5400)
            cadence = 8 if bounded_policy else 32
            if (iteration % cadence == 0 or now-last_save >= 120 or boundary or
                    mid_boundary or stop or reported/norm_rhs <= 1e-6):
                if bounded_policy and iteration % 8 != 0 and not (
                        boundary or mid_boundary or stop or reported/norm_rhs <= 1e-6):
                    # The bounded screens are based on completed 8-step nodes. A
                    # time-based resource sample may still occur here, but it
                    # must not invent an eighth-step node.
                    return 0
                relative, now = snapshot(iteration, current, reported,
                                         terminal=stop)
                if relative <= 1e-6:
                    stop_status = 'TRUE_RESIDUAL_PASS'
                    return int(PETSc.KSP.ConvergedReason.CONVERGED_RTOL)
                if bounded_policy and now >= solve_limit_seconds:
                    # The explicit A6 action and residual assembly are part of
                    # the solve budget, so a post-action overrun is not hidden
                    # behind the callback's earlier timestamp.
                    stop_status = 'PERFORMANCE_CONTROLLED_STOP'
                    return int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
                decision = screen.inspect(iteration, relative, now) if screen_enabled else None
                if stop:
                    stop_status = 'PERFORMANCE_CONTROLLED_STOP'
                elif decision is not None and not decision['passed']:
                    stop_status = decision['status']
                if bounded_policy and stop_status is None:
                    mid_budget = screen.inspect_mid_budget(iteration, relative, now)
                    if mid_budget is not None and not mid_budget['passed']:
                        stop_status = mid_budget['status']
                if stop_status is not None:
                    return int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
            return 0

        ksp.setConvergenceTest(convergence); ksp.setUp(); ksp.solve(rhs, solution)
        iteration = int(ksp.getIterationNumber())
        relative, elapsed = snapshot(iteration, None, ksp.getResidualNorm(), terminal=True)
        final_status = stop_status or 'ITERATION_BUDGET_EXHAUSTED'
        if (bounded_policy and relative > 1e-6 and elapsed >= solve_limit_seconds
                and final_status == 'ITERATION_BUDGET_EXHAUSTED'):
            final_status = 'PERFORMANCE_CONTROLLED_STOP'
        result = dict(final_solution=solution.copy(), final_true_residual=relative,
            iterations=iteration, reason=int(ksp.getConvergedReason()),
            status=final_status, screen=screen.decision,
            snapshots=snapshots, matvec_count=ac.matvec_count, pc_apply_count=pc_context.apply_count,
            explicit_action_count=explicit_count, elapsed_seconds=elapsed,
            ksp_create_count=1, ksp_solve_count=1, ksp_destroy_count=0,
            screen_enabled=screen_enabled,restart=32, max_it=2048, zero_start=True,
            screen_policy=('v9_equal_new_work' if v9_policy else
                           'v7' if v7_policy else 'v5'),
            residual_interval=8 if bounded_policy else 32,
            checkpoint_interval=32,
            mid_budget=screen.mid_budget if bounded_policy else None)
        return result
    finally:
        for value in (ksp, target, solution, operator):
            if value is not None:
                _destroy(value)
                if value is ksp and result is not None:
                    result['ksp_destroy_count'] += 1
