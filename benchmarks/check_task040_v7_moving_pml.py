"""Independent checker for the Task040 moving-PML five-source screen."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from petsc4py import PETSc

from src.solvers.hybrid_moving_pml_screen import (
    MOVING_PML_MANDATORY_CHECKPOINTS,
    MOVING_PML_SCREEN_SCHEMA,
    MOVING_PML_SOURCE_LABELS,
    MOVING_PML_SWEEP,
)

CHECKER_SCHEMA = "task040.v6_5.moving_pml_screen.checker.v1"
FORMAL_SCREEN_SCHEMA = "task040.v6_5.moving_pml_full_state.v1"
_HOLDOUT_TOLERANCE = 32.0 * 2.220446049250313e-16
_NORMAL_REASONS = {
    int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", -3)),
    int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_MAX_IT", -3)),
}

__all__ = ("CHECKER_SCHEMA", "check_moving_pml_screen")


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


def _unstable(reason: Any) -> bool:
    if isinstance(reason, int) and not isinstance(reason, bool):
        return int(reason) < 0 and int(reason) not in _NORMAL_REASONS
    text = str(reason).upper()
    if "DIVERGED_ITS" in text or "DIVERGED_MAX_IT" in text:
        return False
    return any(
        token in text
        for token in (
            "BREAKDOWN",
            "NANORINF",
            "INDEFINITE",
            "PC_FAILED",
            "DIVERGED_NAN",
        )
    )


def _raw_sources(value: Any) -> list[Any] | None:
    if isinstance(value, Mapping):
        value = value.get("sources")
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    return list(value)


def _raw_point(
    source: Mapping[str, Any], iteration: int
) -> tuple[float, bool, bool] | None:
    checkpoints = source.get("checkpoints")
    if not isinstance(checkpoints, Mapping):
        return None
    point = checkpoints.get(str(iteration), checkpoints.get(iteration))
    if not isinstance(point, Mapping) or not isinstance(point.get("finite"), bool):
        return None
    if point.get("not_reached") is True:
        return (
            (float("nan"), False, True)
            if point.get("finite") is False and point.get("value") is None
            else None
        )
    value = point.get(
        "full_true_residual_relative", point.get("true_residual_relative")
    )
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric < 0.0:
        return None
    return numeric, bool(point["finite"]) and math.isfinite(numeric), False


def _recompute(records: Any) -> dict[str, Any]:
    rows = _raw_sources(records)
    if rows is None or len(rows) != 5:
        return _invalid("exactly five moving-PML source records are required")
    if [row.get("label") if isinstance(row, Mapping) else None for row in rows] != list(
        MOVING_PML_SOURCE_LABELS
    ):
        return _invalid("moving-PML source order is not canonical")
    values: dict[str, dict[str, Any]] = {}
    nonfinite = False
    unstable = False
    for label, row in zip(MOVING_PML_SOURCE_LABELS, rows, strict=True):
        if not isinstance(row, Mapping) or not isinstance(row.get("finite"), bool):
            return _invalid(f"source {label} lacks finite")
        reason = row.get("final_reason", row.get("ksp_reason"))
        if reason is None:
            return _invalid(f"source {label} lacks final reason")
        points: dict[str, float] = {}
        source_finite = bool(row["finite"])
        for iteration in MOVING_PML_MANDATORY_CHECKPOINTS:
            point = _raw_point(row, iteration)
            if point is None:
                return _invalid(f"source {label} checkpoint {iteration} is invalid")
            value, finite, not_reached = point
            points[str(iteration)] = value
            source_finite = source_finite and finite and not not_reached
        reason_unstable = _unstable(reason)
        nonfinite = nonfinite or not source_finite
        unstable = unstable or reason_unstable
        r32, r64 = points["32"], points["64"]
        drop = (
            math.log10(r32 / r64)
            if source_finite and r32 > 0.0 and r64 > 0.0
            else None
        )
        values[label] = {
            "r8": points["8"],
            "r16": points["16"],
            "r32": r32,
            "r64": r64,
            "log10_r32_over_r64": drop,
            "finite": source_finite,
            "strongly_unstable": reason_unstable,
            "reason": reason,
        }

    finite = not nonfinite and not unstable
    first = MOVING_PML_SOURCE_LABELS[:3]
    holdouts = MOVING_PML_SOURCE_LABELS[3:]
    strong = bool(
        finite
        and all(values[label]["r64"] <= 0.1 for label in MOVING_PML_SOURCE_LABELS)
        and all(values[label]["r64"] <= 1.0e-2 for label in first)
    )
    weak_baseline = False
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
    positive = bool(not no_signal and (strong or weak_baseline or weak_holdout))
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
        "signal_subclass": "strong" if strong else "weak" if (weak_baseline or weak_holdout) else None,
        "strongly_unstable": unstable,
        "nonfinite": nonfinite,
        "clauses": {
            "strong": strong,
            "weak_v3_2_baseline": weak_baseline,
            "weak_holdout": weak_holdout,
            "holdout_not_worse": holdout_not_worse,
            "no_signal_pair": no_signal_pair,
            "no_signal": no_signal,
        },
        "v3_2_r64_baseline_available": False,
        "sources": values,
    }


def _rank_ready(value: Any, size: int) -> bool:
    if not isinstance(value, list) or len(value) != size:
        return False
    rows = sorted(value, key=lambda row: row.get("rank", -1))
    return [row.get("rank") for row in rows] == list(range(size)) and all(
        isinstance(row.get("ready"), int) and row["ready"] >= 0 for row in rows
    )


def check_moving_pml_screen(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return contract validity separately from the algorithmic route signal."""

    if not isinstance(payload, Mapping):
        return _invalid("moving-PML checker input must be a mapping")
    is_formal = payload.get("schema") == FORMAL_SCREEN_SCHEMA
    raw_payload = payload.get("raw_screen") if is_formal else payload
    if not isinstance(raw_payload, Mapping):
        return _invalid("formal moving-PML result lacks raw_screen mapping")
    checks: dict[str, bool] = {
        "schema": raw_payload.get("schema") == MOVING_PML_SCREEN_SCHEMA,
        "executed": raw_payload.get("executed") is True,
        "mpi_size": raw_payload.get("mpi_size") == 8,
        "source_order": raw_payload.get("source_order")
        == list(MOVING_PML_SOURCE_LABELS),
        "mandatory_checkpoints": raw_payload.get("mandatory_checkpoints")
        == list(MOVING_PML_MANDATORY_CHECKPOINTS),
        "same_setup_action": raw_payload.get("same_setup_action") is True,
        "bare_f_unchanged": bool(
            raw_payload.get("bare_f_unchanged") is True
            and isinstance(raw_payload.get("bare_f_operator_hash_before"), str)
            and bool(raw_payload.get("bare_f_operator_hash_before"))
            and isinstance(raw_payload.get("bare_f_operator_hash_after"), str)
            and bool(raw_payload.get("bare_f_operator_hash_after"))
            and raw_payload.get("bare_f_operator_hash_before")
            == raw_payload.get("bare_f_operator_hash_after")
        ),
    }
    config = raw_payload.get("fixed_configuration")
    checks["fixed_configuration"] = config == {
        "restart": 32,
        "zero_initial_guess": True,
        "pml_profile": "quadratic",
        "integrated_attenuation": 6.0,
        "z_collar_layers": 2,
        "sweep": list(MOVING_PML_SWEEP),
    }
    sources = raw_payload.get("sources")
    one_apply = raw_payload.get("one_apply")
    checks["source_records"] = isinstance(sources, list) and len(sources) == 5
    checks["one_apply"] = isinstance(one_apply, list) and len(one_apply) == 5
    expected_action_before = 0
    checkpoint_keys = {str(value) for value in MOVING_PML_MANDATORY_CHECKPOINTS}
    if checks["source_records"] and checks["one_apply"]:
        for label, source, apply_row in zip(
            MOVING_PML_SOURCE_LABELS, sources, one_apply, strict=True
        ):
            valid = isinstance(source, Mapping) and isinstance(apply_row, Mapping)
            valid = valid and source.get("label") == label and apply_row.get("label") == label
            next_action_before = expected_action_before
            try:
                checkpoints = source["checkpoints"]
                before = int(apply_row["action_apply_count_before"])
                after = int(apply_row["action_apply_count_after"])
                delta = int(apply_row["action_apply_count_delta"])
                valid = valid and before == expected_action_before
                valid = valid and after - before == delta == 1 and before >= 0
                valid = valid and apply_row.get("finite") is True
                valid = valid and all(
                    isinstance(apply_row.get(field), (int, float))
                    and not isinstance(apply_row.get(field), bool)
                    and math.isfinite(float(apply_row[field]))
                    and float(apply_row[field]) >= 0.0
                    for field in (
                        "source_norm",
                        "output_norm",
                        "true_residual_norm",
                        "true_residual_relative",
                    )
                )
                valid = valid and apply_row["true_residual_relative"] == (
                    apply_row["true_residual_norm"]
                    / max(apply_row["source_norm"], 1.0e-300)
                )
                valid = valid and source.get("max_it") == 64
                valid = valid and source.get("restart") == 32
                valid = valid and source.get("zero_initial_guess") is True
                valid = valid and isinstance(checkpoints, Mapping)
                valid = valid and set(checkpoints) == checkpoint_keys
                source_norm = source["source_norm"]
                valid = valid and (
                    isinstance(source_norm, (int, float))
                    and not isinstance(source_norm, bool)
                    and math.isfinite(float(source_norm))
                    and float(source_norm) > 0.0
                )
                f_before = int(source["fgmres_action_apply_count_before"])
                f_after = int(source["fgmres_action_apply_count_after"])
                f_delta = int(source["fgmres_action_apply_count_delta"])
                right_delta = int(source["right_pc_apply_count_delta"])
                valid = valid and f_before == after
                valid = valid and f_after - f_before == f_delta == right_delta
                valid = valid and f_delta >= 0
                next_action_before = f_after
            except (KeyError, TypeError, ValueError):
                valid = False
            expected_action_before = next_action_before
            checks[f"one_apply_{label}"] = valid
    else:
        checks["one_apply_rows"] = False

    mpi_size = int(raw_payload.get("mpi_size") or 0)
    lifecycle = raw_payload.get("factor_lifecycle")
    before = lifecycle.get("before") if isinstance(lifecycle, Mapping) else None
    after = lifecycle.get("after_cleanup") if isinstance(lifecycle, Mapping) else None
    checks["factor_before"] = bool(
        isinstance(before, Mapping)
        and before.get("global_ready") == 3
        and _rank_ready(before.get("rank_ready"), mpi_size)
        and sum(row["ready"] for row in before["rank_ready"]) == 3
    )
    checks["factor_after_cleanup"] = bool(
        isinstance(after, Mapping)
        and after.get("global_ready") == 0
        and after.get("action_destroyed") is True
        and _rank_ready(after.get("rank_ready"), mpi_size)
        and sum(row["ready"] for row in after["rank_ready"]) == 0
        and isinstance(lifecycle, Mapping)
        and lifecycle.get("cleanup") is True
    )
    diagnostics = raw_payload.get("moving_pml_diagnostics")
    checks["factor_diagnostics"] = bool(
        isinstance(diagnostics, Mapping)
        and diagnostics.get("global_auxiliary_matrix") is False
        and diagnostics.get("numeric_allgather") is False
    )
    checks["numeric_replication"] = bool(
        raw_payload.get("numeric_allgather") is False
        and raw_payload.get("full_interface_numeric_replica") is False
    )
    checks["v3_2_r64_baseline_available"] = (
        raw_payload.get("v3_2_r64_baseline_available") is False
    )
    recomputed = _recompute(sources)
    conditional = raw_payload.get("conditional_128")
    if recomputed.get("classification") != "PML_SWEEP_INCONCLUSIVE":
        checks["conditional_128"] = isinstance(conditional, list) and not conditional
        conditional_end = expected_action_before
        checks["conditional_chain"] = True
    else:
        checks["conditional_128"] = isinstance(conditional, list) and len(conditional) == 5
        conditional_end = expected_action_before
        checks["conditional_chain"] = checks["conditional_128"]
        if checks["conditional_128"]:
            for label, row in zip(MOVING_PML_SOURCE_LABELS, conditional, strict=True):
                checkpoints = row.get("checkpoints") if isinstance(row, Mapping) else None
                try:
                    before = int(row["fgmres_action_apply_count_before"])
                    after = int(row["fgmres_action_apply_count_after"])
                    delta = int(row["fgmres_action_apply_count_delta"])
                    right_delta = int(row["right_pc_apply_count_delta"])
                    row_valid = (
                        isinstance(row, Mapping)
                        and row.get("label") == label
                        and row.get("max_it") == 128
                        and row.get("restart") == 32
                        and row.get("zero_initial_guess") is True
                        and before == conditional_end
                        and after - before == delta == right_delta
                        and delta >= 0
                        and isinstance(checkpoints, Mapping)
                        and set(checkpoints) == {"128"}
                        and _raw_point(row, 128) is not None
                    )
                    conditional_end = after
                except (KeyError, TypeError, ValueError):
                    row_valid = False
                checks["conditional_128"] = checks["conditional_128"] and row_valid
                checks["conditional_chain"] = checks["conditional_chain"] and row_valid
    after_diagnostics = raw_payload.get("moving_pml_diagnostics_after_cleanup")
    checks["final_action_apply_count"] = bool(
        isinstance(after_diagnostics, Mapping)
        and isinstance(after_diagnostics.get("apply_count"), int)
        and not isinstance(after_diagnostics.get("apply_count"), bool)
        and after_diagnostics.get("apply_count") == conditional_end
    )
    evidence_valid = bool(recomputed.get("evidence_valid") and all(checks.values()))
    claim_payload = payload if is_formal else raw_payload
    return {
        "schema": CHECKER_SCHEMA,
        "screen_schema": raw_payload.get("schema"),
        "input_schema": payload.get("schema"),
        "status": "checked_moving_pml_screen",
        "evidence_valid": evidence_valid,
        "checker_pass": evidence_valid,
        "pass": bool(evidence_valid and recomputed.get("pass")),
        "classification": recomputed.get("classification", "INVALID_EVIDENCE"),
        "route_signal": recomputed.get("route_signal", "invalid_evidence"),
        "next_required_stage": recomputed.get("next_required_stage", "fix_raw_evidence"),
        "formal_adjudication": False,
        "recomputed": recomputed,
        "evidence_checks": checks,
        "runner_claims": {
            "classification": claim_payload.get("classification"),
            "next_required_stage": claim_payload.get("next_required_stage"),
            "pass": claim_payload.get("pass"),
            "claims_are_authority": False,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = check_moving_pml_screen(payload)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if result["evidence_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
