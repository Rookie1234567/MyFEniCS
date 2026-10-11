"""One retained-space FGMRES, judged by the recovered physical equation.

The evaluator owns the full-space scratch and returns original-equation,
port and recovery residuals. Arnoldi and right-preconditioned directions
remain in the supplied retained space. References are checkpoint-only.
"""

from time import perf_counter

import numpy as np


def run_retained_fgmres(
    rhs, action, pc, *, evaluate, checkpoint, append, seconds,
    resource_sample=lambda: None, stop_requested=lambda: False,
    save_retained=lambda iteration, vector: None,
    restart=32, max_it=2048, residual_interval=8, candidate_rtol=1e-6,
    evaluation_policy=None, retained_tolerance=None, initial_vector=None,
    iterations_consumed=0, true_action=None,
):
    """Callbacks return owned action/PC vectors and plain evaluation facts."""
    from petsc4py import PETSc
    from .fullspace_memory_first_krylov import _ActionContext, _PCContext

    if restart <= 0 or max_it <= 0 or residual_interval <= 0:
        raise ValueError("explicit retained iteration policy")
    if iterations_consumed < 0 or (iterations_consumed and initial_vector is None):
        raise ValueError("continuation requires an explicit validated initial vector")
    original_key = "original_A6_relative" if evaluation_policy is None else evaluation_policy["original_key"]
    ac, pcc = _ActionContext(action), _PCContext(pc)
    sizes = (rhs.getLocalSize(), rhs.getSize())
    operator = solution = target = None
    try:
        operator = PETSc.Mat().createPython((sizes, sizes), context=ac, comm=rhs.getComm())
        operator.setUp()
        solution = operator.createVecRight()
        solution.set(0)
        if initial_vector is not None:
            a = np.asarray(initial_vector)
            if a.shape != (sizes[0],) or not np.isfinite(a).all():
                raise ValueError("explicit retained initial vector shape/finite")
            solution.array[:] = a
        target = solution.duplicate()
        rhs_norm = float(rhs.norm())
        if not np.isfinite(rhs_norm) or rhs_norm <= 0:
            raise ValueError("retained solve requires a finite nonzero physical RHS")
    except BaseException:
        for obj in (target, solution, operator):
            if obj is not None:
                obj.destroy()
        raise
    ksp = None
    snapshots = []
    status = None
    result = None
    last_checkpoint = -1
    last_iteration_seconds = None
    last_evaluated_vector = None
    timings = {"explicit_schur_seconds": 0.0, "physical_evaluation_seconds": 0.0,
               "checkpoint_seconds": 0.0}

    def snapshot(iteration, current, reported, *, terminal=False):
        nonlocal last_checkpoint, last_evaluated_vector
        if current is None:
            solution.copy(target)
        elif iteration == 0:
            solution.copy(target)
        else:
            current.buildSolution(target)
        if (terminal and last_evaluated_vector is not None and snapshots
                and snapshots[-1]['iteration'] == iteration+iterations_consumed
                and np.array_equal(target.array,last_evaluated_vector)):
            save_retained(int(iteration)+iterations_consumed,target)
            return snapshots[-1]
        retained_saved = terminal or iteration % 32 == 0
        if retained_saved:
            save_retained(int(iteration)+iterations_consumed, target)
        started = perf_counter()
        applied = (action if true_action is None else true_action)(target)
        residual = rhs.copy()
        try:
            residual.axpy(-1.0, applied)
            schur_relative = float(residual.norm()) / rhs_norm
            timings["explicit_schur_seconds"] += perf_counter() - started
            started = perf_counter()
            facts = dict(evaluate(target, residual))
            timings["physical_evaluation_seconds"] += perf_counter() - started
        finally:
            applied.destroy(); residual.destroy()
        keys = (("original_A6_relative", "port_closure_relative",
                 "internal_residual_relative", "native_identity_relative", "schur_port_identity_relative")
                if evaluation_policy is None else tuple(evaluation_policy["physical_limits"])+tuple(evaluation_policy["identity_limits"]))
        if not np.isfinite(schur_relative) or any(
                not np.isfinite(float(facts[k])) or float(facts[k]) < 0 for k in keys):
            raise FloatingPointError("nonfinite or negative recovered residual measure")
        if evaluation_policy is None:
            physical_pass = (facts["original_A6_relative"] <= 1e-6
                             and facts["port_closure_relative"] <= 1e-8
                             and facts["internal_residual_relative"] <= 1e-10
                             and facts["native_identity_relative"] <= 1e-10
                             and facts["schur_port_identity_relative"] <= 1e-10)
        else:
            physical_pass = all(facts[k] <= limit for group in ("physical_limits", "identity_limits")
                                for k, limit in evaluation_policy[group].items())
        joint_pass = physical_pass and (retained_tolerance is None or schur_relative <= retained_tolerance)
        row = {**facts, "iteration": int(iteration)+iterations_consumed,
               "ksp_instance_iteration": int(iteration),
               "schur_true_relative_residual": schur_relative,
               "explicit_true_residual": float(facts[original_key]),
               "reported_schur_relative": float(reported) / rhs_norm,
               "solve_seconds": float(seconds()), "physical_residual_pass": physical_pass,
               "solve_gate_pass": joint_pass,
               "solution_source": "terminal_vec_sol" if current is None else "live_buildSolution"}
        snapshots.append(row)
        last_evaluated_vector = target.array.copy()
        append("monitor_residuals.jsonl", row)
        if (terminal or iteration % 32 == 0 or physical_pass) and iteration != last_checkpoint:
            if not retained_saved:
                save_retained(int(iteration)+iterations_consumed, target)
            started = perf_counter()
            checkpoint(int(iteration)+iterations_consumed, target, row)
            timings["checkpoint_seconds"] += perf_counter() - started
            last_checkpoint = int(iteration)
        return row

    try:
        ksp = PETSc.KSP().create(rhs.getComm())
        ksp.setOperators(operator)
        ksp.setType("fgmres")
        ksp.setGMRESRestart(restart)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setInitialGuessNonzero(initial_vector is not None)
        ksp.setTolerances(rtol=0.0, atol=0.0, max_it=max_it)
        ksp.getPC().setType(PETSc.PC.Type.PYTHON)
        ksp.getPC().setPythonContext(pcc)

        def convergence(current, iteration, reported):
            nonlocal status, last_iteration_seconds
            iteration = int(iteration)
            resource_sample()
            solve_seconds = float(seconds())
            step_seconds = (None if last_iteration_seconds is None else
                            solve_seconds - last_iteration_seconds)
            last_iteration_seconds = solve_seconds
            append("iterations.jsonl", {"iteration": iteration+iterations_consumed,
                "ksp_instance_iteration": iteration,
                "reported_schur_relative": float(reported) / rhs_norm,
                "outer_matvec_count": ac.matvec_count, "outer_pc_count": pcc.apply_count,
                "solve_seconds": solve_seconds,
                "step_wall_seconds": step_seconds,
                "timebase": "monotonic_from_solve_start"})
            stop = bool(stop_requested())
            exhausted = iteration >= max_it
            if not np.isfinite(reported):
                status = "NONFINITE_KRYLOV_RESIDUAL"
                return int(PETSc.KSP.ConvergedReason.DIVERGED_NANORINF)
            if iteration % residual_interval == 0 or reported / rhs_norm <= candidate_rtol or stop or exhausted:
                row = snapshot(iteration, current, reported, terminal=stop or exhausted)
                if stop:
                    status = "USER_CONTROLLED_STOP"
                    return int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
                if row["solve_gate_pass"]:
                    status = "TRUE_RESIDUAL_PASS"
                    return int(PETSc.KSP.ConvergedReason.CONVERGED_RTOL)
                identity_fail = ((row["internal_residual_relative"] > 1e-10
                        or row["native_identity_relative"] > 1e-10
                        or row["schur_port_identity_relative"] > 1e-10) if evaluation_policy is None else
                        any(row[k] > limit for k,limit in evaluation_policy["identity_limits"].items()))
                if identity_fail:
                    status = "RECOVERY_IDENTITY_GATE_FAIL"
                    return int(PETSc.KSP.ConvergedReason.DIVERGED_BREAKDOWN)
            if exhausted:
                status = "ITERATION_BUDGET_EXHAUSTED"
                return int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
            return 0

        ksp.setConvergenceTest(convergence)
        ksp.setUp()
        started = perf_counter()
        ksp.solve(rhs, solution)
        ksp_monotonic = perf_counter() - started
        iteration = int(ksp.getIterationNumber())
        final = snapshot(iteration, None, ksp.getResidualNorm(), terminal=True)
        reason = int(ksp.getConvergedReason())
        if status is None:
            status = ("TRUE_RESIDUAL_PASS" if final["solve_gate_pass"] else
                      "ITERATION_BUDGET_EXHAUSTED" if iteration >= max_it else "KRYLOV_BREAKDOWN")
        if status == "TRUE_RESIDUAL_PASS" and not final["solve_gate_pass"]:
            status = "FINAL_PHYSICAL_RESIDUAL_GATE_FAIL"
        result = {"final_solution": solution.copy(), "final_evaluation": final,
            "final_true_residual": final[original_key], "iterations": iteration,
            "reason": reason, "status": status, "snapshots": snapshots,
            "matvec_count": ac.matvec_count, "pc_apply_count": pcc.apply_count,
            "explicit_action_count": len(snapshots), "elapsed_seconds": float(seconds()),
            "ksp_solve_monotonic_seconds": ksp_monotonic, "timings": timings,
            "ksp_create_count": 1, "ksp_solve_count": 1, "ksp_destroy_count": 0,
            "restart": restart, "max_it": max_it, "zero_start": initial_vector is None,
            "iterations_consumed_before_instance": iterations_consumed,
            "cumulative_iterations": iteration+iterations_consumed,
            "continuation_basis": "fresh KSP; previous Krylov basis not retained" if initial_vector is not None else None,
            "zero_start_scope": "retained unknowns; full field includes internal particular solution",
            "retained_local_size": sizes[0], "retained_global_size": sizes[1],
            "residual_interval": residual_interval, "checkpoint_interval": 32,
            "screen_enabled": False, "screen_policy": "v19_fullspace_progress_observed_only",
            "evaluation_policy": evaluation_policy, "retained_target": retained_tolerance,
            "time_policy": "observe_only" if evaluation_policy is None else "explicit_stop_requested",
            "time_gate_evaluated": evaluation_policy is not None}
        return result
    finally:
        for obj in (ksp, target, solution, operator):
            if obj is not None:
                obj.destroy()
        if result is not None:
            result["ksp_destroy_count"] = 1
