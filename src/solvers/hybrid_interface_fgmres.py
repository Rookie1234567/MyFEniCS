"""V3-2 full-span right-FGMRES screen.

This is a research-only screen for the Task040 coupled carrier.  It keeps one
PETSc KSP/PC setup, starts every RHS from zero, and computes the reported
checkpoint residuals independently with the bare operator.  It is deliberately
separate from the frozen V1-1 batch helper because its continuation contract
has an additional 64-iteration phase.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from petsc4py import PETSc

__all__ = (
    "audit_v3_full_side_one_apply",
    "decide_v3_continuation",
    "run_v3_full_span_right_fgmres_batch",
)


class _RightActionContext:
    def __init__(self, action: Any) -> None:
        self.action: Any | None = action
        self.apply_count = 0

    def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.action is None:
            raise RuntimeError("V3 right preconditioner has been destroyed")
        self.action.apply(source, target)
        self.apply_count += 1

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        self.action = None


def _relative(value: float, reference: float) -> float:
    return float(value) / max(float(reference), 1.0e-30)


def _semantic_modal_labels(labels: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        label
        for label in labels
        if "modal_traction_positive" in label
        or "modal_traction_negative" in label
        or "external_dtn_coupling" in label
    )


def _checkpoint_gate(
    phase: Mapping[str, Mapping[str, Any]],
    labels: Sequence[str],
    checkpoint: str,
) -> bool:
    values = {
        label: phase[label].get("checkpoints", {}).get(checkpoint, {})
        for label in labels
    }
    if set(values) != set(labels):
        return False
    if any(row.get("finite") is not True for row in values.values()):
        return False
    residuals = {
        label: row.get("true_residual_relative") for label, row in values.items()
    }
    if any(
        not isinstance(value, (int, float)) or not np.isfinite(float(value))
        for value in residuals.values()
    ):
        return False
    if any(float(value) > 1.0e-2 for value in residuals.values()):
        return False
    strict = _semantic_modal_labels(labels)
    if set(strict) != {
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
    }:
        return False
    return all(float(residuals[label]) <= 1.0e-3 for label in strict)


def _phase1_trend_gate(
    phase: Mapping[str, Mapping[str, Any]], labels: Sequence[str]
) -> dict[str, bool]:
    limit = 10.0 ** (-0.25)
    result: dict[str, bool] = {}
    for label in labels:
        checkpoints = phase[label].get("checkpoints", {})
        r8 = checkpoints.get("8", {}).get("true_residual_relative")
        r16 = checkpoints.get("16", {}).get("true_residual_relative")
        result[label] = bool(
            all(
                checkpoints.get(str(index), {}).get("finite") is True
                for index in (4, 8, 16)
            )
            and isinstance(r8, (int, float))
            and isinstance(r16, (int, float))
            and np.isfinite(float(r8))
            and np.isfinite(float(r16))
            and float(r16) <= limit * float(r8)
            and phase[label].get("ksp_breakdown") is False
        )
    return result


def _phase2_trend_gate(
    phase: Mapping[str, Mapping[str, Any]], labels: Sequence[str]
) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for label in labels:
        row = phase[label]
        checkpoints = row.get("checkpoints", {})
        value = checkpoints.get("32", {}).get("true_residual_relative")
        history = sorted(
            row.get("reported_residual_history", []),
            key=lambda item: int(item.get("iteration", -1)),
        )
        window = [
            item for item in history if 16 <= int(item.get("iteration", -1)) <= 32
        ]
        finite_history = [item.get("relative_residual") for item in window]
        result[label] = bool(
            checkpoints.get("32", {}).get("finite") is True
            and isinstance(value, (int, float))
            and np.isfinite(float(value))
            and [int(item.get("iteration", -1)) for item in window]
            == list(range(16, 33))
            and all(
                isinstance(item, (int, float)) and np.isfinite(float(item))
                for item in finite_history
            )
            and all(
                finite_history[index] <= finite_history[index - 1]
                for index in range(1, len(finite_history))
            )
            and row.get("ksp_breakdown") is False
        )
    return result


def decide_v3_continuation(
    phase1: Mapping[str, Mapping[str, Any]],
    phase2: Mapping[str, Mapping[str, Any]],
    phase3: Mapping[str, Mapping[str, Any]],
    *,
    labels: Sequence[str],
    resource1: Mapping[str, Any],
    resource2: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Derive early/32/64 decisions only from checkpoint evidence."""

    early = next(
        (
            checkpoint
            for checkpoint in ("4", "8", "16")
            if _checkpoint_gate(phase1, labels, checkpoint)
        ),
        None,
    )
    phase1_trend = _phase1_trend_gate(phase1, labels)
    conditional32 = bool(
        early is None and all(phase1_trend.values()) and resource1.get("pass") is True
    )
    phase2_trend = _phase2_trend_gate(phase2, labels) if phase2 else {}
    phase2_pass = bool(phase2 and _checkpoint_gate(phase2, labels, "32"))
    conditional64 = bool(
        conditional32
        and phase2
        and not phase2_pass
        and all(phase2_trend.values())
        and resource2 is not None
        and resource2.get("pass") is True
        and all(
            float(phase2[label]["checkpoints"]["32"]["true_residual_relative"]) <= 0.1
            for label in labels
        )
        and all(
            float(phase2[label]["checkpoints"]["32"]["true_residual_relative"])
            < float(phase1[label]["checkpoints"]["16"]["true_residual_relative"])
            for label in labels
        )
    )
    phase3_pass = bool(phase3 and _checkpoint_gate(phase3, labels, "64"))
    first = (
        int(early)
        if early is not None
        else 32
        if phase2_pass
        else 64
        if phase3_pass
        else None
    )
    return {
        "phase1_trend": phase1_trend,
        "phase2_trend": phase2_trend,
        "phase1_early_preferred_checkpoint": int(early) if early else None,
        "conditional_32_authorized": conditional32,
        "phase2_pass": phase2_pass,
        "conditional_64_authorized": conditional64,
        "phase3_pass": phase3_pass,
        "first_preferred_checkpoint": first,
    }


def audit_v3_full_side_one_apply(
    action: Any,
    bare_operator: PETSc.Mat,
    rhs_by_label: Mapping[str, PETSc.Vec],
    *,
    labels: Sequence[str],
    factor_inventory: Mapping[str, Any],
) -> dict[str, Any]:
    """Audit zero-map, residual, repeat, and linearity for the V3 carrier."""

    labels = tuple(labels)
    if tuple(rhs_by_label) != labels:
        raise ValueError("V3 one-apply labels must be exact and ordered")
    output = bare_operator.createVecLeft()
    residual = bare_operator.createVecLeft()
    combination = bare_operator.createVecLeft()
    expected = bare_operator.createVecLeft()
    zero = bare_operator.createVecRight()
    zero.set(0.0)
    reports: list[dict[str, Any]] = []
    try:
        action.apply(zero, output)
        zero_norm = float(output.norm())
        for label in labels:
            source = rhs_by_label[label]
            first = output.duplicate()
            second = output.duplicate()
            try:
                action.apply(source, first)
                first_coarse = action.diagnostics.get("coarse_residual_last_apply")
                first_coarse_finite = bool(
                    isinstance(first_coarse, (int, float))
                    and np.isfinite(float(first_coarse))
                )
                action.apply(source, second)
                second_coarse = action.diagnostics.get("coarse_residual_last_apply")
                second_coarse_finite = bool(
                    isinstance(second_coarse, (int, float))
                    and np.isfinite(float(second_coarse))
                )
                coarse_repeat = (
                    abs(float(second_coarse) - float(first_coarse))
                    / max(abs(float(first_coarse)), 1.0e-30)
                    if first_coarse_finite and second_coarse_finite
                    else None
                )
                bare_operator.mult(first, residual)
                residual.scale(PETSc.ScalarType(-1.0))
                residual.axpy(PETSc.ScalarType(1.0), source)
                source_norm = float(source.norm())
                output_norm = float(first.norm())
                true_residual_norm = float(residual.norm())
                reports.append(
                    {
                        "label": label,
                        "source_norm": source_norm,
                        "output_norm": output_norm,
                        "true_residual_relative": _relative(
                            true_residual_norm, source_norm
                        ),
                        "true_residual_norm": true_residual_norm,
                        "repeat_relative": 0.0,
                        "first_coarse_residual_relative": first_coarse,
                        "second_coarse_residual_relative": second_coarse,
                        "first_coarse_residual_finite": first_coarse_finite,
                        "second_coarse_residual_finite": second_coarse_finite,
                        "coarse_residual_repeat_relative": coarse_repeat,
                        "coarse_residual_finite": bool(
                            first_coarse_finite and second_coarse_finite
                        ),
                        "finite": bool(
                            np.isfinite(source_norm)
                            and np.isfinite(output_norm)
                            and np.isfinite(true_residual_norm)
                        ),
                    }
                )
                difference = first.duplicate()
                try:
                    first.copy(difference)
                    difference.axpy(PETSc.ScalarType(-1.0), second)
                    reports[-1]["repeat_relative"] = _relative(
                        float(difference.norm()), output_norm
                    )
                finally:
                    difference.destroy()
            finally:
                second.destroy()
                first.destroy()

        if len(labels) >= 2:
            a = rhs_by_label[labels[0]]
            b = rhs_by_label[labels[1]]
            combo = a.duplicate()
            try:
                combo.set(0.0)
                combo.axpy(PETSc.ScalarType(1.25), a)
                combo.axpy(PETSc.ScalarType(-0.4j), b)
                expected.set(0.0)
                action.apply(a, expected)
                expected.scale(PETSc.ScalarType(1.25))
                action.apply(b, combination)
                combination.scale(PETSc.ScalarType(-0.4j))
                expected.axpy(PETSc.ScalarType(1.0), combination)
                action.apply(combo, combination)
                combination.axpy(PETSc.ScalarType(-1.0), expected)
                linearity_relative = _relative(
                    float(combination.norm()), float(expected.norm())
                )
            finally:
                combo.destroy()
        else:
            linearity_relative = 0.0
    finally:
        for vector in (zero, expected, combination, residual, output):
            vector.destroy()

    return {
        "schema": "task040.v3_2.full_side_one_apply.v1",
        "labels": list(labels),
        "reports": reports,
        "zero_output_norm": zero_norm,
        "zero_map_pass": bool(np.isfinite(zero_norm) and zero_norm <= 1.0e-13),
        "repeat_pass": all(
            row["finite"] and row["repeat_relative"] <= 1.0e-10 for row in reports
        ),
        "linearity_relative": linearity_relative,
        "linearity_pass": bool(
            np.isfinite(linearity_relative) and linearity_relative <= 1.0e-10
        ),
        "factor_inventory": dict(factor_inventory),
        "factor_inventory_pass": bool(
            factor_inventory.get("cross_section_group_factor_count") == 3
            and factor_inventory.get("reduced_dense_factor_count") == 1
            and factor_inventory.get("exact_interface_schur_oracle_object_count") == 0
            and factor_inventory.get("full_side_exact_factor_count") == 0
            and factor_inventory.get("global_direct_factor_count") == 0
            and factor_inventory.get("nested_ksp_count") == 0
        ),
        "action_apply_count": int(action.diagnostics.get("apply_count", -1)),
    }


def run_v3_full_span_right_fgmres_batch(
    operator: PETSc.Mat,
    rhs_by_label: Mapping[str, PETSc.Vec],
    right_preconditioner: Any,
    *,
    labels: Sequence[str],
    resource_callback: Callable[[], Mapping[str, Any]] | None = None,
    checkpoint_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run the V3-2 0/4/8/16/32/64 zero-start right-FGMRES screen."""

    if not isinstance(operator, PETSc.Mat):
        raise TypeError("V3 full-span FGMRES requires a PETSc matrix")
    labels = tuple(labels)
    if not labels or tuple(rhs_by_label) != labels:
        raise ValueError("V3 FGMRES labels must be ordered and exact")
    if not callable(getattr(right_preconditioner, "apply", None)):
        raise TypeError("V3 FGMRES requires a fixed right action")
    if any(rhs_by_label[label].getSize() != operator.getSize()[0] for label in labels):
        raise ValueError("V3 FGMRES RHS/operator sizes differ")

    comm = operator.getComm()
    solution = operator.createVecRight()
    monitor = operator.createVecRight()
    residual = operator.createVecLeft()
    pc_context = _RightActionContext(right_preconditioner)
    ksp = PETSc.KSP().create(comm)
    setup_count = 0
    phase1: dict[str, dict[str, Any]] = {}
    phase2: dict[str, dict[str, Any]] = {}
    phase3: dict[str, dict[str, Any]] = {}
    resources: list[dict[str, Any]] = []
    resource3: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    screen_started = time.perf_counter()

    def resource_boundary(name: str) -> dict[str, Any]:
        value = (
            dict(resource_callback())
            if resource_callback is not None
            else {"status": "not_provided", "pass": False}
        )
        value["boundary"] = name
        resources.append(value)
        return value

    def solve_one(
        label: str, rhs: PETSc.Vec, phase: str, max_it: int, wanted: tuple[int, ...]
    ) -> dict[str, Any]:
        solution.set(0.0)
        monitor.set(0.0)
        residual.set(0.0)
        rhs_norm = float(rhs.norm())
        if not np.isfinite(rhs_norm) or rhs_norm <= 1.0e-30:
            raise ValueError(f"V3 mandatory RHS {label} is zero or nonfinite")
        denominator = max(rhs_norm, 1.0e-30)
        checkpoints: dict[str, dict[str, Any]] = {
            "0": {
                "label": label,
                "phase": phase,
                "iteration": 0,
                "reported_relative_residual": 1.0,
                "true_residual_relative": 1.0,
                "finite": True,
            }
        }
        history: list[dict[str, Any]] = []
        true_count = 0
        started_pc_apply_count = pc_context.apply_count

        def add_checkpoint(iteration: int, reported: float, current: PETSc.Vec) -> None:
            nonlocal true_count
            residual.set(0.0)
            operator.mult(current, residual)
            true_count += 1
            residual.axpy(PETSc.ScalarType(-1.0), rhs)
            true = float(residual.norm()) / denominator
            row = {
                "label": label,
                "phase": phase,
                "iteration": int(iteration),
                "reported_relative_residual": float(reported),
                "true_residual_relative": true,
                "true_residual_norm": float(residual.norm()),
                "finite": bool(np.isfinite(float(reported)) and np.isfinite(true)),
            }
            checkpoints[str(iteration)] = row
            if checkpoint_callback is not None:
                checkpoint_callback(row)

        def convergence_test(_current: PETSc.KSP, iteration: int, norm: float) -> int:
            relative = float(norm) / denominator
            history.append({"iteration": int(iteration), "relative_residual": relative})
            if int(iteration) in wanted:
                view = _current.buildSolution(monitor)
                add_checkpoint(
                    int(iteration), relative, monitor if view is None else view
                )
            return 0

        ksp.setTolerances(rtol=0.0, atol=0.0, max_it=int(max_it))
        ksp.setConvergenceTest(convergence_test)
        solve_started = time.perf_counter()
        ksp.solve(rhs, solution)
        residual.set(0.0)
        operator.mult(solution, residual)
        true_count += 1
        residual.axpy(PETSc.ScalarType(-1.0), rhs)
        postsolve_true_residual_norm = float(residual.norm())
        postsolve_true_residual_relative = _relative(
            postsolve_true_residual_norm, rhs_norm
        )
        reason = int(ksp.getConvergedReason())
        iterations = int(ksp.getIterationNumber())
        elapsed_seconds = time.perf_counter() - solve_started
        bounded = {
            int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", -3)),
            int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_MAX_IT", -3)),
        }
        happy_breakdown_reason = int(
            getattr(PETSc.KSP.ConvergedReason, "CONVERGED_HAPPY_BREAKDOWN", 7)
        )
        happy_breakdown = reason == happy_breakdown_reason
        return {
            "label": label,
            "phase": phase,
            "restart": 32,
            "max_it": int(max_it),
            "zero_initial_guess": True,
            "zero_initial_guess_count": 1,
            "reported_residual_history": history,
            "checkpoints": checkpoints,
            "ksp_reason": reason,
            "ksp_breakdown": bool(reason < 0 and reason not in bounded),
            "iterations": iterations,
            "final_iteration": iterations,
            "final_reason": reason,
            "elapsed_seconds": float(elapsed_seconds),
            "postsolve_true_residual_norm": postsolve_true_residual_norm,
            "postsolve_true_residual_relative": postsolve_true_residual_relative,
            "postsolve_true_residual_finite": bool(
                np.isfinite(postsolve_true_residual_norm)
                and np.isfinite(postsolve_true_residual_relative)
            ),
            "happy_breakdown": bool(happy_breakdown),
            "early_stop": bool(iterations < max_it),
            "missing_checkpoints": [
                str(iteration)
                for iteration in wanted
                if str(iteration) not in checkpoints
            ],
            "right_pc_apply_count_delta": int(
                pc_context.apply_count - started_pc_apply_count
            ),
            "right_pc_apply_count_total": int(pc_context.apply_count),
            "true_residual_matvec_count": true_count,
            "shared_ksp": True,
        }

    try:
        ksp.setOperators(operator)
        ksp.setType(PETSc.KSP.Type.FGMRES)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setGMRESRestart(32)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setInitialGuessNonzero(False)
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(pc_context)
        ksp.setUp()
        setup_count = 1
        for label in labels:
            phase1[label] = solve_one(
                label, rhs_by_label[label], "phase1", 16, (4, 8, 16)
            )
        resource1 = resource_boundary("after_phase1")
        initial_decision = decide_v3_continuation(
            phase1,
            {},
            {},
            labels=labels,
            resource1=resource1,
            resource2=None,
        )
        conditional32 = bool(initial_decision["conditional_32_authorized"])
        if conditional32:
            for label in labels:
                phase2[label] = solve_one(
                    label, rhs_by_label[label], "phase2", 32, (32,)
                )
        resource2 = resource_boundary("after_phase2") if conditional32 else None
        decision = decide_v3_continuation(
            phase1,
            phase2,
            {},
            labels=labels,
            resource1=resource1,
            resource2=resource2,
        )
        conditional64 = bool(decision["conditional_64_authorized"])
        if conditional64:
            for label in labels:
                phase3[label] = solve_one(
                    label, rhs_by_label[label], "phase3", 64, (64,)
                )
        if conditional64:
            resource3 = resource_boundary("after_phase3")
        decision = decide_v3_continuation(
            phase1,
            phase2,
            phase3,
            labels=labels,
            resource1=resource1,
            resource2=resource2,
        )
        result = {
            "schema": "task040.v3_2.full_span_right_fgmres.v1",
            "labels": list(labels),
            "phase1": phase1,
            "phase1_trend": decision["phase1_trend"],
            "phase1_early_preferred_checkpoint": decision[
                "phase1_early_preferred_checkpoint"
            ],
            "first_preferred_checkpoint": decision["first_preferred_checkpoint"],
            "resource_boundaries": resources,
            "resource3": resource3,
            "conditional_32_authorized": conditional32,
            "phase2": phase2,
            "phase2_trend": decision["phase2_trend"],
            "phase2_pass": decision["phase2_pass"],
            "conditional_64_authorized": conditional64,
            "phase3": phase3,
            "phase3_pass": decision["phase3_pass"],
            "ksp_setup_count": setup_count,
            "ksp_destroy_count": 0,
            "right_pc_apply_count": pc_context.apply_count,
            "zero_initial_guess_all_rhs": True,
            "single_right_pc_setup": True,
            "research_only": True,
            "wall_seconds": float(time.perf_counter() - screen_started),
        }
    finally:
        ksp.destroy()
        pc_context.destroy()
        residual.destroy()
        monitor.destroy()
        solution.destroy()
        if result is not None:
            result["ksp_destroy_count"] = 1
            result["ksp_destroyed"] = True
    if result is None:
        raise RuntimeError("V3 FGMRES screen did not produce a result")
    return result
