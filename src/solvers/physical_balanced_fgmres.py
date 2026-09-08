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


def run_balanced_fgmres(rhs, action, pc, *, checkpoint, append, seconds,
                       resource_sample=lambda: None, stop_requested=lambda: False,
                       screen_enabled=True, solve_limit_seconds=7200):
    """Callbacks own action/PC outputs; seconds is a conservative shared clock.

    Exactly one KSP creation and one solve, max2048/restart32/zero start.
    Convergence is decided by explicit true residuals from buildSolution while
    KSP is active. Once solve returns, use vec_sol directly, never build again.
    """
    if not np.isfinite(solve_limit_seconds) or solve_limit_seconds <= 0:
        raise ValueError('positive finite solve limit required')
    from petsc4py import PETSc
    from .fullspace_memory_first_krylov import _ActionContext, _PCContext
    from .fullspace_physical_intermediate import _destroy
    ac, pc_context = _ActionContext(action), _PCContext(pc)
    sizes = (rhs.getLocalSize(), rhs.getSize())
    operator = PETSc.Mat().createPython((sizes, sizes), context=ac, comm=rhs.getComm())
    ksp = solution = target = None
    screen = BalancedScreen()
    snapshots = []
    explicit_count = 0
    last_save = -120.
    stop_status = None
    last_checkpoint_iteration = -1
    result = None
    norm_rhs = max(float(rhs.norm()), np.finfo(float).tiny)

    def snapshot(iteration, current, reported):
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
            if iteration != last_checkpoint_iteration:
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
            boundary = screen_enabled and screen.decision is None and (iteration >= 128 or now >= 1800)
            if iteration % 32 == 0 or now-last_save >= 120 or boundary or stop or reported/norm_rhs <= 1e-6:
                relative, now = snapshot(iteration, current, reported)
                if relative <= 1e-6:
                    stop_status = 'TRUE_RESIDUAL_PASS'
                    return int(PETSc.KSP.ConvergedReason.CONVERGED_RTOL)
                decision = screen.inspect(iteration, relative, now) if screen_enabled else None
                if stop:
                    stop_status = 'PERFORMANCE_CONTROLLED_STOP'
                elif decision is not None and not decision['passed']:
                    stop_status = decision['status']
                if stop_status is not None:
                    return int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
            return 0

        ksp.setConvergenceTest(convergence); ksp.setUp(); ksp.solve(rhs, solution)
        iteration = int(ksp.getIterationNumber())
        relative, elapsed = snapshot(iteration, None, ksp.getResidualNorm())
        result = dict(final_solution=solution.copy(), final_true_residual=relative,
            iterations=iteration, reason=int(ksp.getConvergedReason()),
            status=stop_status or 'ITERATION_BUDGET_EXHAUSTED', screen=screen.decision,
            snapshots=snapshots, matvec_count=ac.matvec_count, pc_apply_count=pc_context.apply_count,
            explicit_action_count=explicit_count, elapsed_seconds=elapsed,
            ksp_create_count=1, ksp_solve_count=1, ksp_destroy_count=0,
            screen_enabled=screen_enabled,restart=32, max_it=2048, zero_start=True)
        return result
    finally:
        for value in (ksp, target, solution, operator):
            if value is not None:
                _destroy(value)
                if value is ksp and result is not None:
                    result['ksp_destroy_count'] += 1
