"""One retained-space FGMRES, judged by the recovered physical equation.

The evaluator owns the full-space scratch and returns original-equation,
port and recovery residuals. Arnoldi and right-preconditioned directions
remain in the supplied retained space. References are checkpoint-only.
"""

from time import perf_counter, perf_counter_ns
import sys

import numpy as np


def run_retained_fgmres(
    rhs, action, pc, *, evaluate, checkpoint, append, seconds,
    resource_sample=lambda: None, stop_requested=lambda: False,
    save_retained=lambda iteration, vector: None,
    persist_native_stop_records=False,
):
    """Callbacks return owned action/PC vectors and plain evaluation facts."""
    from petsc4py import PETSc
    from .fullspace_memory_first_krylov import _ActionContext, _PCContext

    ac, pcc = _ActionContext(action), _PCContext(pc)
    sizes = (rhs.getLocalSize(), rhs.getSize())
    operator = solution = target = None
    try:
        operator = PETSc.Mat().createPython((sizes, sizes), context=ac, comm=rhs.getComm())
        operator.setUp()
        solution = operator.createVecRight()
        solution.set(0)
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
    primary_stop_record = None
    ksp_solve_record = None
    last_checkpoint = -1
    ksp_start_monotonic_ns = None
    ksp_end_monotonic_ns = None
    timings = {"explicit_schur_seconds": 0.0, "physical_evaluation_seconds": 0.0,
               "checkpoint_seconds": 0.0}

    def finite_json_number(value):
        try:
            converted = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return converted if np.isfinite(converted) else None

    def record_primary_stop(
        iteration,
        gate,
        reported,
        proposed_reason,
        applied_status,
        row=None,
        extra_metrics=None,
    ):
        nonlocal primary_stop_record
        if not persist_native_stop_records or primary_stop_record is not None:
            return
        reported_value = finite_json_number(reported)
        metrics = {
            "reported_schur_residual_norm": reported_value,
            "reported_schur_residual_finite": reported_value is not None,
            "reported_schur_residual_repr": repr(reported),
        }
        if row is not None:
            for key in (
                "reported_schur_relative",
                "schur_true_relative_residual",
                "original_A6_relative",
                "port_closure_relative",
                "internal_residual_relative",
                "native_identity_relative",
                "schur_port_identity_relative",
            ):
                metrics[key] = finite_json_number(row.get(key))
            metrics["physical_residual_pass"] = bool(
                row.get("physical_residual_pass", False)
            )
        if extra_metrics:
            metrics.update(extra_metrics)
        record = {
            "schema": "task40extra.retained_ksp_primary_stop.v1",
            "iteration": int(iteration),
            "gate": str(gate),
            "raw_metrics": metrics,
            "policy": {
                "ksp_rtol": 0.0,
                "ksp_atol": 0.0,
                "max_it": 2048,
                "original_A6_relative_max": 1.0e-6,
                "port_closure_relative_max": 1.0e-8,
                "internal_residual_relative_max": 1.0e-10,
                "native_identity_relative_max": 1.0e-10,
                "schur_port_identity_relative_max": 1.0e-10,
                "residual_interval": 8,
                "checkpoint_interval": 32,
                "time_policy": "observe_only",
            },
            "applied_status": str(applied_status),
            "proposed_petsc_reason": int(proposed_reason),
        }
        append("primary_stop.jsonl", record)
        primary_stop_record = record

    def record_followup_failure(phase, exc):
        if not persist_native_stop_records:
            return
        record = {
            "schema": "task40extra.retained_ksp_followup_failure.v1",
            "phase": str(phase),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "primary_stop_record_status": (
                "persisted" if primary_stop_record is not None else "unknown_or_not_reached"
            ),
            "ksp_solve_record_status": (
                "persisted" if ksp_solve_record is not None else "unknown_or_not_reached"
            ),
        }
        try:
            append("ksp_followup_failures.jsonl", record)
        except BaseException as write_exc:
            if hasattr(exc, "add_note"):
                exc.add_note(
                    "failed to append follow-up failure record: "
                    f"{type(write_exc).__name__}: {write_exc}"
                )

    def read_native_int(label, getter):
        try:
            return int(getter()), None
        except Exception as exc:
            return "unknown", {
                "error_type": type(exc).__name__,
                "error": str(exc),
                "field": label,
            }

    def capture_ksp_solve_phase(*, solve_returned, solve_error=None):
        nonlocal ksp_solve_record
        reason, reason_read_error = read_native_int(
            "converged_reason", ksp.getConvergedReason
        )
        iteration, iteration_read_error = read_native_int(
            "iteration_count", ksp.getIterationNumber
        )
        elapsed = (
            ksp_end_monotonic_ns - ksp_start_monotonic_ns
        ) / 1.0e9
        record = {
            "schema": "task40extra.retained_ksp_solve_phase.v1",
            "scope": "PETSc.KSP.solve_only",
            "solve_returned": bool(solve_returned),
            "start_monotonic_ns": int(ksp_start_monotonic_ns),
            "end_monotonic_ns": int(ksp_end_monotonic_ns),
            "ksp_solve_monotonic_seconds": float(elapsed),
            "converged_reason": reason,
            "iteration_count": iteration,
            "outer_matvec_count": int(ac.matvec_count),
            "outer_pc_apply_count": int(pcc.apply_count),
            "explicit_action_count": len(snapshots),
            "read_errors": {
                key: value
                for key, value in (
                    ("converged_reason", reason_read_error),
                    ("iteration_count", iteration_read_error),
                )
                if value is not None
            },
        }
        if solve_error is not None:
            record["solve_error"] = {
                "error_type": type(solve_error).__name__,
                "error": str(solve_error),
            }
        if persist_native_stop_records:
            append("ksp_solve_phase.jsonl", record)
            ksp_solve_record = record
        return reason, iteration, float(elapsed)

    def snapshot(iteration, current, reported, *, terminal=False, before_checkpoint=None):
        nonlocal last_checkpoint, status
        if current is None:
            solution.copy(target)
        elif iteration == 0:
            target.set(0)
        else:
            current.buildSolution(target)
        retained_saved = terminal or iteration % 32 == 0
        if retained_saved:
            save_retained(int(iteration), target)
        started = perf_counter()
        applied = action(target)
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
        keys = ("original_A6_relative", "port_closure_relative",
                "internal_residual_relative", "native_identity_relative", "schur_port_identity_relative")
        if persist_native_stop_records:
            missing = [key for key in keys if key not in facts]
            if missing:
                status = "RECOVERY_METRIC_FIELDS_MISSING"
                record_primary_stop(
                    iteration,
                    "required_recovery_metrics_present",
                    reported,
                    PETSc.KSP.ConvergedReason.DIVERGED_BREAKDOWN,
                    status,
                    extra_metrics={"missing_fields": missing},
                )
                raise KeyError(
                    "retained evaluation is missing required residual metrics: "
                    + ", ".join(missing)
                )
            metric_values = {}
            invalid = []
            for key in keys:
                try:
                    value = float(facts[key])
                except (TypeError, ValueError, OverflowError):
                    value = None
                metric_values[key] = value
                if value is None or not np.isfinite(value) or value < 0.0:
                    invalid.append(key)
            if not np.isfinite(schur_relative):
                invalid.append("schur_true_relative_residual")
                metric_values["schur_true_relative_residual"] = float(
                    schur_relative
                )
            if invalid:
                nonfinite = any(
                    metric_values.get(key) is None
                    or not np.isfinite(metric_values.get(key, 0.0))
                    for key in invalid
                )
                status = (
                    "NONFINITE_RECOVERY_RESIDUAL"
                    if nonfinite
                    else "INVALID_RECOVERY_RESIDUAL"
                )
                proposed_reason = (
                    PETSc.KSP.ConvergedReason.DIVERGED_NANORINF
                    if nonfinite
                    else PETSc.KSP.ConvergedReason.DIVERGED_BREAKDOWN
                )
                record_primary_stop(
                    iteration,
                    "recovered_residual_metrics_finite_nonnegative",
                    reported,
                    proposed_reason,
                    status,
                    row=facts,
                    extra_metrics={
                        "invalid_fields": invalid,
                        "raw_values": {
                            key: {
                                "value": finite_json_number(
                                    metric_values.get(key)
                                ),
                                "repr": repr(
                                    facts.get(key)
                                    if key != "schur_true_relative_residual"
                                    else schur_relative
                                ),
                            }
                            for key in invalid
                        },
                    },
                )
                raise FloatingPointError(
                    "nonfinite, negative, or nonnumeric recovered residual measure: "
                    + ", ".join(invalid)
                )
        elif not np.isfinite(schur_relative) or any(
            not np.isfinite(float(facts[k])) or float(facts[k]) < 0 for k in keys
        ):
            raise FloatingPointError("nonfinite or negative recovered residual measure")
        physical_pass = (facts["original_A6_relative"] <= 1e-6
                         and facts["port_closure_relative"] <= 1e-8
                         and facts["internal_residual_relative"] <= 1e-10
                         and facts["native_identity_relative"] <= 1e-10
                         and facts["schur_port_identity_relative"] <= 1e-10)
        row = {**facts, "iteration": int(iteration),
               "schur_true_relative_residual": schur_relative,
               "explicit_true_residual": float(facts["original_A6_relative"]),
               "reported_schur_relative": float(reported) / rhs_norm,
               "solve_seconds": float(seconds()), "physical_residual_pass": physical_pass,
               "solution_source": "terminal_vec_sol" if current is None else "live_buildSolution"}
        if before_checkpoint is not None:
            before_checkpoint(row)
        snapshots.append(row)
        append("monitor_residuals.jsonl", row)
        if (terminal or iteration % 32 == 0 or physical_pass) and iteration != last_checkpoint:
            if not retained_saved:
                save_retained(int(iteration), target)
            started = perf_counter()
            checkpoint(int(iteration), target, row)
            timings["checkpoint_seconds"] += perf_counter() - started
            last_checkpoint = int(iteration)
        return row

    try:
        ksp = PETSc.KSP().create(rhs.getComm())
        ksp.setOperators(operator)
        ksp.setType("fgmres")
        ksp.setGMRESRestart(32)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setInitialGuessNonzero(False)
        ksp.setTolerances(rtol=0.0, atol=0.0, max_it=2048)
        ksp.getPC().setType(PETSc.PC.Type.PYTHON)
        ksp.getPC().setPythonContext(pcc)

        def convergence(current, iteration, reported):
            nonlocal status
            iteration = int(iteration)
            resource_sample()
            append("iterations.jsonl", {"iteration": iteration,
                "reported_schur_relative": float(reported) / rhs_norm,
                "outer_matvec_count": ac.matvec_count, "outer_pc_count": pcc.apply_count})
            stop = bool(stop_requested())
            if not np.isfinite(reported):
                status = "NONFINITE_KRYLOV_RESIDUAL"
                proposed_reason = int(PETSc.KSP.ConvergedReason.DIVERGED_NANORINF)
                record_primary_stop(
                    iteration,
                    "reported_krylov_residual_finite",
                    reported,
                    proposed_reason,
                    status,
                )
                return proposed_reason
            if stop:
                status = "USER_CONTROLLED_STOP"
                proposed_reason = int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
                record_primary_stop(
                    iteration,
                    "user_controlled_stop_requested",
                    reported,
                    proposed_reason,
                    status,
                )
                snapshot(iteration, current, reported, terminal=True)
                return proposed_reason
            if iteration % 8 == 0 or reported / rhs_norm <= 1e-6 or stop:
                decision = {"reason": None}

                def classify_snapshot(row):
                    nonlocal status
                    if row["physical_residual_pass"]:
                        status = "TRUE_RESIDUAL_PASS"
                        decision["reason"] = int(
                            PETSc.KSP.ConvergedReason.CONVERGED_RTOL
                        )
                        gate = "full_physical_residual_pass"
                    elif (
                        row["internal_residual_relative"] > 1e-10
                        or row["native_identity_relative"] > 1e-10
                        or row["schur_port_identity_relative"] > 1e-10
                    ):
                        status = "RECOVERY_IDENTITY_GATE_FAIL"
                        decision["reason"] = int(
                            PETSc.KSP.ConvergedReason.DIVERGED_BREAKDOWN
                        )
                        gate = "recovery_identity_strict_gate"
                    else:
                        return
                    record_primary_stop(
                        iteration,
                        gate,
                        reported,
                        decision["reason"],
                        status,
                        row,
                    )

                snapshot(
                    iteration,
                    current,
                    reported,
                    before_checkpoint=classify_snapshot,
                )
                if decision["reason"] is not None:
                    return decision["reason"]
            return 0

        ksp.setConvergenceTest(convergence)
        ksp.setUp()
        ksp_start_monotonic_ns = perf_counter_ns()
        try:
            ksp.solve(rhs, solution)
        except BaseException as exc:
            ksp_end_monotonic_ns = perf_counter_ns()
            try:
                capture_ksp_solve_phase(solve_returned=False, solve_error=exc)
            except BaseException as write_exc:
                if hasattr(exc, "add_note"):
                    exc.add_note(
                        "failed to persist the exceptional KSP phase record: "
                        f"{type(write_exc).__name__}: {write_exc}"
                    )
            record_followup_failure("ksp_solve", exc)
            raise
        ksp_end_monotonic_ns = perf_counter_ns()
        try:
            reason, iteration, ksp_monotonic = capture_ksp_solve_phase(
                solve_returned=True
            )
        except BaseException as exc:
            record_followup_failure("ksp_solve_phase_persistence", exc)
            raise
        if iteration == "unknown":
            exc = RuntimeError("PETSc KSP iteration count is unknown after solve")
            record_followup_failure("postsolve_iteration_count_unknown", exc)
            raise exc
        try:
            final = snapshot(int(iteration), None, ksp.getResidualNorm(), terminal=True)
        except BaseException as exc:
            record_followup_failure("terminal_snapshot", exc)
            raise
        if status is None:
            status = ("TRUE_RESIDUAL_PASS" if final["physical_residual_pass"] else
                      "ITERATION_BUDGET_EXHAUSTED" if iteration >= 2048 else "KRYLOV_BREAKDOWN")
        if status == "TRUE_RESIDUAL_PASS" and not final["physical_residual_pass"]:
            status = "FINAL_PHYSICAL_RESIDUAL_GATE_FAIL"
        result = {"final_solution": solution.copy(), "final_evaluation": final,
            "final_true_residual": final["original_A6_relative"], "iterations": iteration,
            "reason": reason, "status": status, "snapshots": snapshots,
            "matvec_count": ac.matvec_count, "pc_apply_count": pcc.apply_count,
            "explicit_action_count": len(snapshots), "elapsed_seconds": float(seconds()),
            "ksp_solve_monotonic_seconds": ksp_monotonic, "timings": timings,
            "ksp_phase": {
                "scope": "PETSc.KSP.solve_only",
                "start_monotonic_ns": int(ksp_start_monotonic_ns),
                "end_monotonic_ns": int(ksp_end_monotonic_ns),
                "elapsed_seconds": float(ksp_monotonic),
                "excludes": [
                    "KSP setup",
                    "terminal residual snapshot",
                    "outer adapter cache validation and packet saves",
                ],
            },
            "elapsed_seconds_scope": (
                "retained_outer_solve_clock_through_terminal_snapshot"
            ),
            "ksp_create_count": 1, "ksp_solve_count": 1, "ksp_destroy_count": 0,
            "restart": 32, "max_it": 2048, "zero_start": True,
            "zero_start_scope": "retained unknowns; full field includes internal particular solution",
            "retained_local_size": sizes[0], "retained_global_size": sizes[1],
            "residual_interval": 8, "checkpoint_interval": 32,
            "screen_enabled": False, "screen_policy": "v19_fullspace_progress_observed_only",
            "time_policy": "observe_only", "time_gate_evaluated": False}
        return result
    finally:
        active_exception = sys.exc_info()[1]
        destroy_errors = []
        for obj in (ksp, target, solution, operator):
            if obj is not None:
                try:
                    obj.destroy()
                except BaseException as exc:
                    destroy_errors.append(exc)
                    record_followup_failure("petsc_object_destroy", exc)
        if result is not None:
            result["ksp_destroy_count"] = 1 if not destroy_errors else 0
        if destroy_errors and active_exception is None:
            raise destroy_errors[0]
