"""Small moving-PML five-source screen over the borrowed bare-F operator.

The screen owns only the supplied moving-PML action during its run.  The bare
operator and source vectors remain caller-owned.  Classification is a narrow
V6.5 gate helper; the independent benchmark checker re-computes it from the
raw checkpoints before accepting any route signal.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from petsc4py import PETSc

from .hybrid_side_impedance import _petsc_matrix_hash

MOVING_PML_SCREEN_SCHEMA = "task040.v6_5.moving_pml_screen.v1"
MOVING_PML_SOURCE_LABELS = (
    "modal_traction_positive",
    "modal_traction_negative",
    "external_dtn_coupling",
    "fixed_random_repeat_0",
    "fixed_random_repeat_1",
)
MOVING_PML_MANDATORY_CHECKPOINTS = (8, 16, 32, 64)
MOVING_PML_CONDITIONAL_CHECKPOINTS = (128,)
MOVING_PML_SWEEP = (0, 1, 2, 2, 1, 0)
_SAFE = 1.0e-300
_HOLDOUT_TOLERANCE = 32.0 * np.finfo(float).eps

__all__ = (
    "MOVING_PML_CONDITIONAL_CHECKPOINTS",
    "MOVING_PML_MANDATORY_CHECKPOINTS",
    "MOVING_PML_SCREEN_SCHEMA",
    "MOVING_PML_SOURCE_LABELS",
    "MOVING_PML_SWEEP",
    "classify_moving_pml_screen",
    "run_v7_moving_pml_full_state",
)


def _invalid(message: str) -> dict[str, Any]:
    return {
        "evidence_valid": False,
        "checker_pass": False,
        "pass": False,
        "classification": "INVALID_EVIDENCE",
        "route_signal": "invalid_evidence",
        "next_required_stage": "fix_raw_evidence",
        "error": str(message),
    }


def _source_list(records: Any) -> list[Any] | None:
    if isinstance(records, Mapping):
        records = records.get("sources")
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        return None
    return list(records)


def _reason_is_strongly_unstable(reason: Any) -> bool:
    normal = {
        int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", -3)),
        int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_MAX_IT", -3)),
    }
    if isinstance(reason, (int, np.integer)):
        return int(reason) < 0 and int(reason) not in normal
    text = str(reason).upper()
    if "DIVERGED_ITS" in text or "DIVERGED_MAX_IT" in text:
        return False
    return any(
        marker in text
        for marker in (
            "BREAKDOWN",
            "NANORINF",
            "INDEFINITE",
            "PC_FAILED",
            "DIVERGED_NAN",
        )
    )


def _checkpoint(record: Mapping[str, Any], iteration: int) -> Mapping[str, Any] | None:
    checkpoints = record.get("checkpoints")
    if not isinstance(checkpoints, Mapping):
        return None
    value = checkpoints.get(str(iteration), checkpoints.get(iteration))
    return value if isinstance(value, Mapping) else None


def _missing_checkpoint(iteration: int) -> dict[str, Any]:
    return {
        "iteration": int(iteration),
        "not_reached": True,
        "finite": False,
        "value": None,
        "full_true_residual_relative": None,
    }


def classify_moving_pml_screen(
    records: Any, *, v3_2_r64_baseline: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Recompute the fixed five-source PML route from raw true residuals."""

    rows = _source_list(records)
    if rows is None or len(rows) != len(MOVING_PML_SOURCE_LABELS):
        return _invalid("moving-PML screen requires exactly five source records")
    if [row.get("label") if isinstance(row, Mapping) else None for row in rows] != list(
        MOVING_PML_SOURCE_LABELS
    ):
        return _invalid("moving-PML source order is not the fixed five-source order")

    values: dict[str, dict[str, Any]] = {}
    nonfinite = False
    unstable = False
    for label, row in zip(MOVING_PML_SOURCE_LABELS, rows, strict=True):
        if not isinstance(row, Mapping) or not isinstance(row.get("finite"), bool):
            return _invalid(f"moving-PML source {label} lacks a boolean finite field")
        reason = row.get("final_reason", row.get("ksp_reason"))
        if reason is None:
            return _invalid(f"moving-PML source {label} lacks a KSP reason")
        points: dict[str, float] = {}
        point_finite = bool(row["finite"])
        for iteration in MOVING_PML_MANDATORY_CHECKPOINTS:
            point = _checkpoint(row, iteration)
            if point is None or not isinstance(point.get("finite"), bool):
                return _invalid(f"moving-PML source {label} lacks checkpoint {iteration}")
            if point.get("not_reached") is True:
                if point["finite"] is not False:
                    return _invalid(
                        f"moving-PML source {label} has invalid not-reached checkpoint"
                    )
                points[str(iteration)] = float("nan")
                point_finite = False
                continue
            try:
                value = float(
                    point.get(
                        "full_true_residual_relative",
                        point.get("true_residual_relative"),
                    )
                )
            except (TypeError, ValueError):
                return _invalid(
                    f"moving-PML source {label} checkpoint {iteration} is not numeric"
                )
            if value < 0.0:
                return _invalid(
                    f"moving-PML source {label} checkpoint {iteration} is negative"
                )
            points[str(iteration)] = value
            point_finite = point_finite and bool(point["finite"]) and np.isfinite(value)
        strongly_unstable = _reason_is_strongly_unstable(reason)
        nonfinite = nonfinite or not point_finite
        unstable = unstable or strongly_unstable
        r32, r64 = points["32"], points["64"]
        drop = (
            float(np.log10(r32 / r64))
            if point_finite and r32 > 0.0 and r64 > 0.0
            else None
        )
        values[label] = {
            "r8": points["8"],
            "r16": points["16"],
            "r32": r32,
            "r64": r64,
            "log10_r32_over_r64": drop,
            "finite": point_finite,
            "strongly_unstable": strongly_unstable,
            "reason": reason,
        }

    first = MOVING_PML_SOURCE_LABELS[:3]
    holdouts = MOVING_PML_SOURCE_LABELS[3:]
    finite = not nonfinite and not unstable
    strong = bool(
        finite
        and all(values[label]["r64"] <= 0.1 for label in MOVING_PML_SOURCE_LABELS)
        and all(values[label]["r64"] <= 1.0e-2 for label in first)
    )
    baseline_weak = False
    if isinstance(v3_2_r64_baseline, Mapping):
        baseline_weak = bool(
            finite
            and all(
                label in v3_2_r64_baseline
                and np.isfinite(float(v3_2_r64_baseline[label]))
                and float(v3_2_r64_baseline[label]) > 0.0
                and values[label]["r64"] <= float(v3_2_r64_baseline[label]) / 4.0
                for label in MOVING_PML_SOURCE_LABELS
            )
        )
    holdout_not_worse = bool(
        finite
        and all(
            values[label]["r64"]
            <= values[label]["r32"]
            + _HOLDOUT_TOLERANCE
            * max(1.0, abs(values[label]["r32"]), abs(values[label]["r64"]))
            for label in holdouts
        )
    )
    weak_holdout = bool(
        finite
        and all(values[label]["r64"] <= 0.5 for label in first)
        and holdout_not_worse
    )
    external = values["external_dtn_coupling"]
    random0 = values["fixed_random_repeat_0"]
    no_signal_pair = bool(
        finite
        and external["r64"] > 0.8
        and random0["r64"] > 0.8
        and isinstance(external["log10_r32_over_r64"], float)
        and isinstance(random0["log10_r32_over_r64"], float)
        and external["log10_r32_over_r64"] < 0.10
        and random0["log10_r32_over_r64"] < 0.10
    )
    no_signal = bool(nonfinite or unstable or no_signal_pair)
    positive = bool(not no_signal and (strong or baseline_weak or weak_holdout))
    if positive:
        classification = "PML_SWEEP_STRONG_OR_WEAK_POSITIVE"
        route_signal = "factor_free_local_service_required"
        next_stage = "factor_free_local_service_required"
    elif no_signal:
        classification = "PML_SWEEP_NO_SIGNAL"
        route_signal = "adaptive_schwarz_required"
        next_stage = "adaptive_schwarz_required"
    else:
        classification = "PML_SWEEP_INCONCLUSIVE"
        route_signal = "inconclusive"
        next_stage = "inconclusive"
    return {
        "evidence_valid": True,
        "checker_pass": True,
        "pass": positive,
        "classification": classification,
        "route_signal": route_signal,
        "next_required_stage": next_stage,
        "signal_subclass": "strong" if strong else "weak" if (baseline_weak or weak_holdout) else None,
        "strongly_unstable": unstable,
        "nonfinite": nonfinite,
        "clauses": {
            "strong": strong,
            "weak_v3_2_baseline": baseline_weak,
            "weak_holdout": weak_holdout,
            "holdout_not_worse": holdout_not_worse,
            "no_signal_pair": no_signal_pair,
            "no_signal": no_signal,
        },
        "sources": values,
    }


class _RightActionContext:
    def __init__(self, action: Any) -> None:
        self.action = action
        self.apply_count = 0

    def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.action is None:
            raise RuntimeError("moving-PML right action is unavailable")
        self.action.apply(source, target)
        self.apply_count += 1

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        self.action = None


def _resource(callback: Callable[[], Mapping[str, Any]] | None, boundary: str) -> dict[str, Any]:
    if callback is None:
        return {"boundary": boundary, "status": "not_provided", "pass": False}
    value = callback()
    if not isinstance(value, Mapping):
        raise TypeError("moving-PML resource callback must return a mapping")
    return {"boundary": boundary, **dict(value)}


def _solve_source(
    ksp: PETSc.KSP,
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    context: _RightActionContext,
    action: Any,
    label: str,
    max_it: int,
    wanted: Sequence[int],
) -> dict[str, Any]:
    solution = operator.createVecRight()
    monitor = operator.createVecRight()
    residual = operator.createVecLeft()
    started = time.perf_counter()
    try:
        solution.set(0.0)
        monitor.set(0.0)
        residual.set(0.0)
        rhs_norm = float(rhs.norm())
        denominator = max(rhs_norm, _SAFE)
        checkpoints: dict[str, dict[str, Any]] = {}
        history: list[dict[str, Any]] = []

        def checkpoint(current: PETSc.KSP, iteration: int, reported: float) -> None:
            view = current.buildSolution(monitor)
            candidate = monitor if view is None else view
            operator.mult(candidate, residual)
            residual.axpy(PETSc.ScalarType(-1.0), rhs)
            true_norm = float(residual.norm())
            true_relative = true_norm / denominator
            checkpoints[str(iteration)] = {
                "label": label,
                "iteration": int(iteration),
                "reported_relative_residual": float(reported),
                "full_true_residual_norm": true_norm,
                "full_true_residual_relative": true_relative,
                "finite": bool(
                    np.isfinite(reported)
                    and np.isfinite(true_norm)
                    and np.isfinite(true_relative)
                ),
            }

        def convergence_test(current: PETSc.KSP, iteration: int, norm: float) -> int:
            reported = float(norm) / denominator
            history.append(
                {"iteration": int(iteration), "reported_relative_residual": reported}
            )
            if int(iteration) in wanted:
                checkpoint(current, int(iteration), reported)
            return 0

        before = int(action.diagnostics.get("apply_count", 0))
        context_before = int(context.apply_count)
        ksp.setTolerances(rtol=0.0, atol=0.0, max_it=int(max_it))
        ksp.setConvergenceTest(convergence_test)
        ksp.solve(rhs, solution)
        iterations = int(ksp.getIterationNumber())
        reason = int(ksp.getConvergedReason())
        checkpoint_nonfinite = any(
            not bool(point.get("finite"))
            for point in checkpoints.values()
        )
        if (
            _reason_is_strongly_unstable(reason)
            or checkpoint_nonfinite
            or not np.isfinite(rhs_norm)
        ):
            for iteration in wanted:
                checkpoints.setdefault(
                    str(int(iteration)), _missing_checkpoint(int(iteration))
                )
        after = int(action.diagnostics.get("apply_count", 0))
        return {
            "label": label,
            "max_it": int(max_it),
            "restart": 32,
            "zero_initial_guess": True,
            "ksp_reason": reason,
            "final_reason": reason,
            "iterations": iterations,
            "reported_residual_history": history,
            "checkpoints": checkpoints,
            "finite": bool(
                np.isfinite(rhs_norm)
                and np.all(
                    [bool(row["finite"]) for row in checkpoints.values()]
                )
            ),
            "source_norm": rhs_norm,
            "solution_norm": float(solution.norm()),
            "right_pc_apply_count_delta": int(context.apply_count - context_before),
            "fgmres_action_apply_count_before": before,
            "fgmres_action_apply_count_after": after,
            "fgmres_action_apply_count_delta": after - before,
            "elapsed_seconds": float(time.perf_counter() - started),
        }
    finally:
        residual.destroy()
        monitor.destroy()
        solution.destroy()


def _one_apply_record(
    operator: PETSc.Mat, action: Any, rhs: PETSc.Vec, label: str
) -> dict[str, Any]:
    output = operator.createVecLeft()
    residual = operator.createVecLeft()
    try:
        before = int(action.diagnostics.get("apply_count", 0))
        source_norm = float(rhs.norm())
        action.apply(rhs, output)
        after = int(action.diagnostics.get("apply_count", 0))
        operator.mult(output, residual)
        residual.axpy(PETSc.ScalarType(-1.0), rhs)
        residual_norm = float(residual.norm())
        output_norm = float(output.norm())
        return {
            "label": label,
            "action_apply_count_before": before,
            "action_apply_count_after": after,
            "action_apply_count_delta": after - before,
            "source_norm": source_norm,
            "output_norm": output_norm,
            "true_residual_norm": residual_norm,
            "true_residual_relative": residual_norm / max(source_norm, _SAFE),
            "finite": bool(
                np.isfinite(source_norm)
                and np.isfinite(output_norm)
                and np.isfinite(residual_norm)
            ),
        }
    finally:
        residual.destroy()
        output.destroy()


def run_v7_moving_pml_full_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run the fixed five-source moving-PML screen on a live setup."""

    if not isinstance(payload, Mapping):
        raise TypeError("moving-PML screen payload must be a mapping")
    operator = payload.get("bare_operator")
    action = payload.get("moving_action")
    rhs_by_label = payload.get("rhs_by_label")
    if not isinstance(operator, PETSc.Mat) or not callable(getattr(action, "apply", None)):
        raise TypeError("moving-PML screen requires bare_operator and moving_action")
    if not isinstance(rhs_by_label, Mapping) or list(rhs_by_label) != list(
        MOVING_PML_SOURCE_LABELS
    ):
        raise ValueError("moving-PML screen requires the fixed five source mapping")
    comm = operator.getComm().tompi4py()
    started = time.perf_counter()
    bare_hash_before = _petsc_matrix_hash(operator)
    action_before = dict(action.diagnostics)
    local_ready = sum(
        int(group.get("core_factor_count", 0))
        for group in action_before.get("groups", ())
        if isinstance(group, Mapping)
    )
    rank_ready_before = comm.allgather(
        {"rank": int(comm.rank), "ready": int(local_ready)}
    )
    context = _RightActionContext(action)
    ksp = PETSc.KSP().create(operator.getComm())
    sources: list[dict[str, Any]] = []
    conditional: list[dict[str, Any]] = []
    one_apply: list[dict[str, Any]] = []
    resource_before: dict[str, Any] = {}
    result: dict[str, Any] | None = None
    try:
        resource_before = _resource(payload.get("resource_callback"), "before_screen")
        ksp.setOperators(operator)
        ksp.setType(PETSc.KSP.Type.FGMRES)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setGMRESRestart(32)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setInitialGuessNonzero(False)
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(context)
        ksp.setUp()
        for label in MOVING_PML_SOURCE_LABELS:
            one_apply.append(
                _one_apply_record(operator, action, rhs_by_label[label], label)
            )
            record = _solve_source(
                ksp,
                operator,
                rhs_by_label[label],
                context,
                action,
                label,
                64,
                MOVING_PML_MANDATORY_CHECKPOINTS,
            )
            sources.append(record)
        initial = classify_moving_pml_screen(sources)
        if (
            initial["classification"] == "PML_SWEEP_INCONCLUSIVE"
            and initial["evidence_valid"]
            and all(bool(record.get("finite")) for record in sources)
        ):
                for label, record in zip(
                    MOVING_PML_SOURCE_LABELS, sources, strict=True
                ):
                    conditional.append(
                        _solve_source(
                            ksp,
                            operator,
                            rhs_by_label[label],
                            context,
                            action,
                            label,
                            128,
                            MOVING_PML_CONDITIONAL_CHECKPOINTS,
                        )
                    )
        resource_after = _resource(payload.get("resource_callback"), "after_screen")
        bare_hash_after = _petsc_matrix_hash(operator)
        result = {
            "schema": MOVING_PML_SCREEN_SCHEMA,
            "executed": True,
            "mpi_size": int(comm.size),
            "source_order": list(MOVING_PML_SOURCE_LABELS),
            "mandatory_checkpoints": list(MOVING_PML_MANDATORY_CHECKPOINTS),
            "conditional_checkpoints": list(MOVING_PML_CONDITIONAL_CHECKPOINTS),
            "sources": sources,
            "conditional_128": conditional,
            "one_apply": one_apply,
            "fixed_configuration": {
                "restart": 32,
                "zero_initial_guess": True,
                "pml_profile": "quadratic",
                "integrated_attenuation": 6.0,
                "z_collar_layers": 2,
                "sweep": list(MOVING_PML_SWEEP),
            },
            "same_setup_action": True,
            "bare_f_operator_hash_before": bare_hash_before,
            "bare_f_operator_hash_after": bare_hash_after,
            "bare_f_unchanged": bare_hash_before == bare_hash_after,
            "factor_lifecycle": {
                "before": {
                    "global_ready": int(sum(item["ready"] for item in rank_ready_before)),
                    "rank_ready": rank_ready_before,
                },
                "after_cleanup": None,
                "cleanup": False,
            },
            "moving_pml_diagnostics": action_before,
            "resource": {"before": resource_before, "after": resource_after},
            "source_build_audits": payload.get("source_build_audits", {}),
            "initial_classification": initial,
            "classification": initial["classification"],
            "next_required_stage": initial["next_required_stage"],
            "pass": bool(initial["pass"]),
            "screen_positive": bool(initial["pass"]),
            "formal_adjudication": False,
            "v3_2_r64_baseline_available": False,
            "numeric_allgather": False,
            "full_interface_numeric_replica": False,
            "wall_seconds": float(time.perf_counter() - started),
        }
    finally:
        ksp.destroy()
        context.destroy()
        action.destroy()
        rank_ready_after = comm.allgather(
            {"rank": int(comm.rank), "ready": 0}
        )
        cleanup = {
            "global_ready": int(sum(item["ready"] for item in rank_ready_after)),
            "rank_ready": rank_ready_after,
            "action_destroyed": bool(action.diagnostics.get("destroyed")),
        }
        if result is not None:
            result["factor_lifecycle"]["after_cleanup"] = cleanup
            result["factor_lifecycle"]["cleanup"] = True
            result["moving_pml_diagnostics_after_cleanup"] = action.diagnostics
    if result is None:
        raise RuntimeError("moving-PML screen did not produce a result")
    return result
