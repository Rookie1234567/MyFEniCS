"""Small raw-field checker for the Task39extra V25 formal records.

The worker summary is an evidence container, not an authority.  This checker
recomputes the BAL_H and p4 counts from every saved boundary call and applies
the residual/identity gates independently of the worker's final status.  It
does not construct a solver or start a PDE.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping


CHECKER_SCHEMA = "task039extra.v25.dynamic-checker.v1"
VERSIONED_CHECKER_SCHEMA = "task039extra.versioned-dynamic-checker.v2"
TRUE_RESIDUAL_LIMIT = 1.0e-6
NATIVE_AQ_LIMIT = 1.0e-10
BEST_FINITE_EXHAUSTION_PROFILE = "physical_p6_trace_a4_tensor_h6_v29"
V29_A4_IMPLEMENTATION = "fused_sum_factorized_partial_assembly_full_A4"
V29_A4_ORACLE = "native_ffcx_full_A4_same_p4_forms_and_dtn"
NATIVE_A4_IMPLEMENTATION = "native_ffcx_full_A4"

BACKEND = "isotropic_sum_factorized_n1e_v26"
H6_BACKEND = "isotropic_sum_factorized_n1e_v26_apply_and_power10"
THREAD_CONTRACT = "mpi1_omp1_blas1_v25"
V30_PROFILE = "physical_p6_trace_workstation_guided_v30"
V31_PROFILE = "physical_p6_trace_projection_layout_v31"
VERSIONED_PROFILES = {V30_PROFILE, V31_PROFILE}
# Frozen V30/V31 original-h7.5 N1E-hex identity from the reviewed compact audit.
V30_V31_COMPONENT_IDENTITY = {
    "quadrature_degree": 15,
    "quadrature_rule": "default",
    "points": 512,
    "quadrature_shape": [8, 8, 8],
    "points_sha256": "dfd7f88ca358f9ef5a1a48bbd8b09e080b0bc24ce6215cb74718bd13dd5e2fc0",
    "weights_sha256": "5eedb32c5e648bf31a102add0c230ccd7513f59b75fc28b21dd2c613db1ef09d",
    "coefficient_matrix_shape": [882, 1029],
    "coefficient_matrix_sha256": "cd4160e6ec6da0cc50738183c8f0544098f70695f2a8cdd4b867b49210db3799",
}


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _number(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} is boolean")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is not an integer") from exc
    if isinstance(value, float) and (not math.isfinite(value) or value != number):
        raise ValueError(f"{label} is not an integer")
    if isinstance(value, str) and str(number) != value.strip():
        raise ValueError(f"{label} is not an integer")
    if number < 0:
        raise ValueError(f"{label} is negative")
    return number


def _positive_integer(value: Any) -> bool:
    try:
        return _number(value, "count") > 0
    except ValueError:
        return False


def _positive_number(value: Any) -> bool:
    return _finite(value) and float(value) > 0.0


def _fused_batch_counts_close(
    volume_action: Mapping[str, Any], fused_volume: Mapping[str, Any]
) -> bool:
    """Recompute fused per-batch work from the live cell/apply counters."""

    try:
        cells = _number(fused_volume.get("cell_count"), "fused.cell_count")
        batch_size = _number(
            fused_volume.get("batch_size"), "fused.batch_size"
        )
        full_applies = _number(
            fused_volume.get("full_apply_count"), "fused.full_apply_count"
        )
        component_applies = _number(
            fused_volume.get("component_apply_count"),
            "fused.component_apply_count",
        )
        curl_applies = _number(
            fused_volume.get("curl_component_apply_count"),
            "fused.curl_component_apply_count",
        )
        mass_applies = _number(
            fused_volume.get("mass_component_apply_count"),
            "fused.mass_component_apply_count",
        )
        all_applies = _number(fused_volume.get("apply_count"), "fused.apply_count")
        volume_applies = _number(
            volume_action.get("apply_count"), "volume.apply_count"
        )
    except ValueError:
        return False
    if cells < 1 or batch_size < 1 or all_applies < 1:
        return False
    batches_per_apply = (cells + batch_size - 1) // batch_size
    expected_batches = batches_per_apply * all_applies
    try:
        return bool(
            all_applies == full_applies + component_applies
            and component_applies == curl_applies + mass_applies
            and full_applies == volume_applies
            and _number(fused_volume.get("gather_count"), "fused.gather_count")
            == expected_batches
            and _number(
                fused_volume.get("coefficient_forward_count"),
                "fused.coefficient_forward_count",
            )
            == expected_batches
            and _number(
                fused_volume.get("coefficient_backward_count"),
                "fused.coefficient_backward_count",
            )
            == expected_batches
            and _number(
                fused_volume.get("scatter_count"), "fused.scatter_count"
            )
            == expected_batches
            and _number(
                fused_volume.get("curl_integral_count"),
                "fused.curl_integral_count",
            )
            == batches_per_apply * (full_applies + curl_applies)
            and _number(
                fused_volume.get("mass_integral_count"),
                "fused.mass_integral_count",
            )
            == batches_per_apply * (full_applies + mass_applies)
        )
    except ValueError:
        return False


def _path(record: Mapping[str, Any], *parts: str) -> Any:
    value: Any = record
    for part in parts:
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _boundary_records(summary: Mapping[str, Any]) -> list[Any]:
    records = _path(summary, "pc", "boundary_records")
    if not isinstance(records, list):
        return []
    return list(records)


def _raw_call_facts(
    call: Any, label: str, *, allow_soft_return: bool = False
) -> tuple[dict[str, Any], list[str]]:
    """Read one p4 call and recompute its repair residuals from raw records."""

    failures: list[str] = []
    if not isinstance(call, Mapping):
        return {}, [f"{label}.not_object"]
    inner = call.get("inner")
    if not isinstance(inner, Mapping):
        return {}, [f"{label}.inner_missing"]
    repair = inner.get("repair")
    if not isinstance(repair, Mapping):
        return {}, [f"{label}.repair_missing"]
    try:
        logical = _number(
            repair.get("logical_p4_apply_count", inner.get("p4_logical_apply_count")),
            f"{label}.logical",
        )
        actual = _number(
            repair.get("actual_mat_solve_count", inner.get("p4_mat_solve_count")),
            f"{label}.mat_solve",
        )
    except ValueError as exc:
        return {}, [str(exc)]
    if logical != 1:
        failures.append(f"{label}.logical_p4_apply_count_not_one")
    implementation = call.get("a4_action_implementation", inner.get("a4_action_implementation"))
    oracle = call.get("a4_action_oracle", inner.get("a4_action_oracle"))
    allowed_a4_identities = {
        (V29_A4_IMPLEMENTATION, V29_A4_ORACLE),
        (NATIVE_A4_IMPLEMENTATION, NATIVE_A4_IMPLEMENTATION),
    }
    if allow_soft_return and (implementation, oracle) not in allowed_a4_identities:
        failures.append(f"{label}.a4_action_identity_mismatch")
    rhs_norm = repair.get("rhs_norm", call.get("rhs_norm", inner.get("rhs_norm")))
    if not _finite(rhs_norm):
        failures.append(f"{label}.rhs_norm_missing_or_nonfinite")
        rhs_norm_value = math.nan
    else:
        rhs_norm_value = float(rhs_norm)
        if rhs_norm_value < 0.0:
            failures.append(f"{label}.rhs_norm_negative")
    nonzero_logical = logical if _finite(rhs_norm) and rhs_norm_value != 0.0 else 0

    records = repair.get("records")
    if not isinstance(records, list):
        failures.append(f"{label}.repair_records_not_list")
        records = []
    reported_extra = repair.get("extra_solve_count")
    try:
        extra = _number(reported_extra, f"{label}.extra_solve_count")
    except ValueError as exc:
        failures.append(str(exc))
        extra = -1
    if not 0 <= extra <= 2:
        failures.append(f"{label}.extra_solve_count_out_of_range")
    correction_count = sum(
        1
        for item in records
        if isinstance(item, Mapping) and item.get("phase") == "correction"
    )
    if correction_count != extra:
        failures.append(f"{label}.correction_record_count_mismatch")
    if len(records) != 1 + max(extra, 0):
        failures.append(f"{label}.repair_record_count_mismatch")
    expected_actual = nonzero_logical + max(extra, 0)
    expected_physical = logical + max(extra, 0)
    if actual != expected_actual:
        failures.append(f"{label}.mat_solve_formula_mismatch")
    try:
        a4_action_count = _number(
            repair.get("native_A4_action_count", inner.get("native_A4_actions")),
            f"{label}.a4_action_count",
        )
    except ValueError as exc:
        failures.append(str(exc))
        a4_action_count = -1
    if a4_action_count != expected_physical:
        failures.append(f"{label}.a4_action_count_mismatch")
    if allow_soft_return and (
        repair.get("a4_action_implementation"), repair.get("a4_action_oracle")
    ) != (implementation, oracle):
        failures.append(f"{label}.repair_a4_action_identity_mismatch")
    best_snapshot_bytes = 0
    selected_evidence_bytes = 0
    if allow_soft_return:
        try:
            best_snapshot_bytes = _number(
                repair.get("best_snapshot_peak_local_bytes"),
                f"{label}.best_snapshot_peak_local_bytes",
            )
            selected_evidence_bytes = _number(
                repair.get("selected_evidence_copy_local_bytes"),
                f"{label}.selected_evidence_copy_local_bytes",
            )
        except ValueError as exc:
            failures.append(str(exc))
        if best_snapshot_bytes < 0 or selected_evidence_bytes < 0:
            failures.append(f"{label}.negative_repair_memory_bytes")
    if not records:
        failures.append(f"{label}.mat_solve_has_no_raw_records")
    if inner.get("p4_mat_solve_count") is not None:
        try:
            if _number(inner["p4_mat_solve_count"], f"{label}.inner_mat_solve") != actual:
                failures.append(f"{label}.inner_mat_solve_mismatch")
        except ValueError as exc:
            failures.append(str(exc))

    residual_rows: list[dict[str, Any]] = []
    phases = [item.get("phase") if isinstance(item, Mapping) else None for item in records]
    if phases and (phases[0] != "raw" or any(phase != "correction" for phase in phases[1:])):
        failures.append(f"{label}.repair_phase_order")
    for index, item in enumerate(records):
        if not isinstance(item, Mapping):
            failures.append(f"{label}.repair_record[{index}].not_object")
            continue
        expected_delta = 0 if index == 0 and nonzero_logical == 0 else 1
        if item.get("factor_solve_call_delta") != expected_delta:
            failures.append(f"{label}.repair_record[{index}].factor_solve_call_delta")
        if index > 0 and item.get("index") != index:
            failures.append(f"{label}.repair_record[{index}].index")
        record_rhs = item.get("rhs_norm", rhs_norm_value)
        residual_norm = item.get("residual_norm")
        if not _finite(record_rhs) or not _finite(residual_norm):
            failures.append(f"{label}.repair_record[{index}].nonfinite_residual_fields")
            continue
        if float(record_rhs) < 0.0 or float(residual_norm) < 0.0:
            failures.append(f"{label}.repair_record[{index}].negative_residual_field")
        denominator = max(float(rhs_norm_value), sys.float_info.min)
        ratio = float(residual_norm) / denominator
        if rhs_norm_value != 0.0 and not math.isclose(
            float(record_rhs), rhs_norm_value, rel_tol=1.0e-12, abs_tol=1.0e-14
        ):
            failures.append(f"{label}.repair_record[{index}].rhs_norm_mismatch")
        if rhs_norm_value == 0.0 and float(residual_norm) != 0.0:
            failures.append(f"{label}.zero_rhs_nonzero_residual")
        reported_ratio = item.get("relative_residual")
        if not _finite(reported_ratio) or not math.isclose(
            float(reported_ratio), ratio, rel_tol=1.0e-12, abs_tol=1.0e-25
        ):
            failures.append(f"{label}.repair_record[{index}].relative_residual_mismatch")
        residual_rows.append(
            {
                "phase": item.get("phase"),
                "rhs_norm": rhs_norm_value,
                "residual_norm": float(residual_norm),
                "recomputed_relative": ratio,
                "reported_relative": reported_ratio,
                "factor_solve_call_delta": item.get("factor_solve_call_delta"),
            }
        )
    factor_delta_sum = sum(
        int(item.get("factor_solve_call_delta", 0))
        for item in records
        if isinstance(item, Mapping)
        and isinstance(item.get("factor_solve_call_delta"), int)
    )
    if factor_delta_sum != actual:
        failures.append(f"{label}.factor_solve_delta_sum_mismatch")
    last_ratio = residual_rows[-1]["recomputed_relative"] if residual_rows else math.nan
    selected_index = min(
        range(len(residual_rows)),
        key=lambda index: (residual_rows[index]["recomputed_relative"], index),
        default=-1,
    )
    min_ratio = (
        residual_rows[selected_index]["recomputed_relative"]
        if selected_index >= 0 else math.nan
    )
    if allow_soft_return:
        try:
            reported_selected = _number(
                repair.get("selected_attempt"), f"{label}.selected_attempt"
            )
        except ValueError as exc:
            failures.append(str(exc))
            reported_selected = -1
        if reported_selected != selected_index:
            failures.append(f"{label}.selected_attempt_not_argmin_tie_earliest")
        final_ratio = min_ratio
        for key, expected in (
            ("returned_rho", final_ratio),
            ("last_attempt_rho", last_ratio),
            ("min_rho", min_ratio),
        ):
            reported = repair.get(key)
            if not _finite(reported) or not math.isclose(
                float(reported), expected, rel_tol=1.0e-12, abs_tol=1.0e-25
            ):
                failures.append(f"{label}.{key}_mismatch")
        if final_ratio > 1.0e-10:
            if extra != 2 or repair.get("status") != "COARSE_TARGET_UNMET_CONTINUE":
                failures.append(f"{label}.soft_exhaustion_status_or_count_mismatch")
        elif repair.get("status") != (
            "REFINED_TARGET_MET" if extra else "NOT_NEEDED"
        ):
            failures.append(f"{label}.soft_target_met_status_mismatch")
    else:
        final_ratio = last_ratio
        if final_ratio > 1.0e-10:
            failures.append(f"{label}.final_Aq_residual_limit")
    for key, value in (
        ("final_relative_residual", final_ratio),
        ("native_A4_relative_residual", final_ratio),
    ):
        reported = repair.get(key) if key == "final_relative_residual" else call.get(key)
        if reported is not None and (
            not _finite(reported)
            or not math.isclose(float(reported), value, rel_tol=1.0e-12, abs_tol=1.0e-25)
        ):
            failures.append(f"{label}.{key}_mismatch")
    return {
        "logical_units": logical,
        "nonzero_logical_units": nonzero_logical,
        "nonzero_logical": nonzero_logical > 0,
        "rhs_norm": rhs_norm_value,
        "actual_mat_solve": actual,
        "physical_f4_calls": expected_physical,
        "a4_action_count": a4_action_count,
        "a4_action_implementation": implementation,
        "a4_action_oracle": oracle,
        "best_snapshot_peak_local_bytes": best_snapshot_bytes,
        "selected_evidence_copy_local_bytes": selected_evidence_bytes,
        "extra_repairs": max(extra, 0),
        "repair_records": len(records),
        "residuals": residual_rows,
        "final_recomputed_relative": final_ratio,
        "last_attempt_recomputed_relative": last_ratio,
        "selected_attempt": selected_index,
        "coarse_target_met": _finite(final_ratio) and final_ratio <= 1.0e-10,
    }, failures


def _raw_bal_h_facts(
    summary: Mapping[str, Any],
    stage: str | None = None,
    *,
    allow_soft_return: bool = False,
) -> dict[str, Any]:
    """Recompute the one-pass boundary ledger and split setup/check/solve."""

    boundaries = _boundary_records(summary)
    failures: list[str] = []
    rows: list[dict[str, Any]] = []

    def read_boundary(boundary: Any, index: int) -> None:
        if not isinstance(boundary, Mapping):
            failures.append(f"boundary[{index}].not_object")
            return
        pc = boundary.get("pc")
        if not isinstance(pc, Mapping):
            failures.append(f"boundary[{index}].pc_missing")
            return
        if pc.get("route") != "BAL_H":
            failures.append(f"boundary[{index}].route_not_BAL_H")
        if boundary.get("completed") is not True:
            failures.append(f"boundary[{index}].not_completed")
        balance = pc.get("inexact_balance")
        calls = balance.get("calls") if isinstance(balance, Mapping) else None
        if not isinstance(calls, list):
            failures.append(f"boundary[{index}].calls_missing")
            return
        if len(calls) != 2:
            failures.append(f"boundary[{index}].BAL_H_coarse_call_count_not_two")
        for call_index, call in enumerate(calls, start=1):
            facts, call_failures = _raw_call_facts(
                call,
                f"boundary[{index}].call[{call_index}]",
                allow_soft_return=allow_soft_return,
            )
            failures.extend(call_failures)
            if facts:
                facts.update({"boundary": index, "call": call_index})
                rows.append(facts)

    for index, boundary in enumerate(boundaries, start=1):
        read_boundary(boundary, index)

    setup_counts = _path(summary, "x1_setup_checks", "setup_pc_counts")
    setup_counts = setup_counts if isinstance(setup_counts, Mapping) else {}
    try:
        setup_count = _number(setup_counts.get("bal_h"), "setup.bal_h")
    except ValueError as exc:
        failures.append(str(exc))
        setup_count = None

    actual = _path(summary, "solver", "retained_outer", "actual_first_arnoldi")
    pair = actual.get("pair") if isinstance(actual, Mapping) else None
    if isinstance(pair, Mapping):
        variants = pair.get("variants")
        if not isinstance(variants, Mapping) or not variants:
            failures.append("check.first_direction_pair_variants_missing")
            check_count = 0
        else:
            check_count = 0
            for name, variant in variants.items():
                if not isinstance(variant, Mapping) or variant.get("pc_apply_delta") != 1:
                    failures.append(f"check.{name}.pc_apply_delta")
                else:
                    check_count += 1
    elif isinstance(actual, Mapping) and actual.get("passed") is True:
        check_count = 1
    else:
        check_count = 0
        failures.append("check.actual_first_arnoldi_missing")

    solver = summary.get("solver") if isinstance(summary.get("solver"), Mapping) else {}
    try:
        iteration_count = _number(solver.get("pc_apply_count"), "solver.pc_apply_count")
    except ValueError as exc:
        failures.append(str(exc))
        iteration_count = None
    expected_boundary_count = (setup_count or 0) + check_count + (iteration_count or 0)
    if len(boundaries) != expected_boundary_count:
        failures.append("boundary.phase_count_closure")
    if iteration_count is not None and len(boundaries) - (setup_count or 0) - check_count != iteration_count:
        failures.append("iteration.pc_apply_count_mismatch")

    phase_names = ["setup", "check", "iteration"]
    phase_rows = {
        phase: [] for phase in phase_names
    }
    for index, row in enumerate(rows):
        boundary_index = int(row["boundary"])
        if boundary_index <= (setup_count or 0):
            phase = "setup"
        elif boundary_index <= (setup_count or 0) + check_count:
            phase = "check"
        else:
            phase = "iteration"
        row["phase"] = phase
        phase_rows[phase].append(row)

    # The X1 packet is a cross-check only.  It must agree with the first raw
    # boundary's two calls, but it is deliberately not counted a second time.
    x1_records = setup_counts.get("p4_call_records")
    if not isinstance(x1_records, list):
        failures.append("setup.x1_p4_call_records_missing")
    else:
        # X1 stores a copy of the setup calls.  It is a cross-check, never a
        # second source of BAL_H or p4 totals.
        raw_setup_calls = [row for row in rows if row["phase"] == "setup"]
        if len(x1_records) != len(raw_setup_calls):
            failures.append("setup.x1_p4_call_records_count_mismatch")

    def totals(items: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "p4_raw_call_records": len(items),
            "logical_units": sum(int(row["logical_units"]) for row in items),
            "nonzero_logical_units": sum(int(row["nonzero_logical_units"]) for row in items),
            "actual_mat_solve": sum(int(row["actual_mat_solve"]) for row in items),
            "physical_f4_calls": sum(int(row["physical_f4_calls"]) for row in items),
            "a4_action_count": sum(int(row["a4_action_count"]) for row in items),
            "best_snapshot_peak_local_bytes": max(
                (int(row["best_snapshot_peak_local_bytes"]) for row in items), default=0
            ),
            "selected_evidence_copy_local_bytes": max(
                (int(row["selected_evidence_copy_local_bytes"]) for row in items), default=0
            ),
            "extra_repairs": sum(int(row["extra_repairs"]) for row in items),
        }

    phase_totals = {phase: totals(phase_rows[phase]) for phase in phase_names}
    all_totals = totals(rows)
    returned = sorted(
        float(row["final_recomputed_relative"])
        for row in rows
        if _finite(row.get("final_recomputed_relative"))
    )

    def quantile(fraction: float) -> float | None:
        if not returned:
            return None
        index = max(0, math.ceil(fraction * len(returned)) - 1)
        return returned[min(index, len(returned) - 1)]

    coarse_target_met_all = bool(rows) and all(
        row["coarse_target_met"] for row in rows
    )
    coarse_unmet_continued_count = sum(
        not row["coarse_target_met"] for row in rows
    )
    if all_totals["actual_mat_solve"] != (
        all_totals["nonzero_logical_units"] + all_totals["extra_repairs"]
    ):
        failures.append("mat_solve_nonzero_logical_plus_repairs_mismatch")
    if allow_soft_return:
        verification = _path(summary, "formal_release_timing", "a4_verification")
        if not isinstance(verification, Mapping):
            failures.append("formal_release_timing.a4_verification_missing")
        else:
            selected_audit = verification.get("selected_action_audit")
            construction = verification.get("candidate_construction_facts")
            repair_workspace = verification.get("soft_repair_workspace")
            repair_workspace = repair_workspace if isinstance(repair_workspace, Mapping) else {}
            action_count_start = verification.get("selected_action_apply_count_start")
            action_count_end = verification.get("selected_action_apply_count_end")
            implementation = verification.get("implementation")
            oracle_identity = verification.get("oracle_identity")
            identities = {
                (row.get("a4_action_implementation"), row.get("a4_action_oracle"))
                for row in rows
            }
            candidate_selected = (
                implementation == V29_A4_IMPLEMENTATION
                and oracle_identity == V29_A4_ORACLE
            )
            native_fallback_selected = (
                implementation == NATIVE_A4_IMPLEMENTATION
                and oracle_identity == NATIVE_A4_IMPLEMENTATION
            )
            checks = {
                "implementation": candidate_selected or native_fallback_selected,
                "all_calls_use_selected_action": identities == {(implementation, oracle_identity)},
                "action_count": verification.get("action_count") == all_totals["a4_action_count"],
                "selected_audit_count": isinstance(selected_audit, Mapping)
                and selected_audit.get("apply_count") == action_count_end
                and _finite(action_count_start)
                and _finite(action_count_end)
                and float(action_count_end) - float(action_count_start)
                == all_totals["a4_action_count"],
                "construction_facts": (
                    isinstance(construction, Mapping)
                    and construction.get("implementation_identity") == V29_A4_IMPLEMENTATION
                    and construction.get("oracle_identity") == V29_A4_ORACLE
                    and construction.get("degree") == 4
                    and construction.get("action_role") == "full_A4_verification_candidate"
                ) if candidate_selected else (
                    native_fallback_selected and construction == {}
                ),
                "repair_workspace_enabled": repair_workspace.get("enabled") is True,
                "repair_workspace_vector_reserve": repair_workspace.get(
                    "reserved_coarse_vector_upper_count"
                ) == 24,
                "repair_workspace_covers_snapshots": (
                    _finite(repair_workspace.get("reserved_bytes"))
                    and _finite(repair_workspace.get("best_snapshot_upper_bytes"))
                    and _finite(repair_workspace.get("selected_evidence_copy_upper_bytes"))
                    and float(repair_workspace["reserved_bytes"])
                    >= float(repair_workspace["best_snapshot_upper_bytes"])
                    + float(repair_workspace["selected_evidence_copy_upper_bytes"])
                    and float(repair_workspace["best_snapshot_upper_bytes"])
                    >= all_totals["best_snapshot_peak_local_bytes"]
                    and float(repair_workspace["selected_evidence_copy_upper_bytes"])
                    >= all_totals["selected_evidence_copy_local_bytes"]
                ),
            }
            failures.extend(
                f"formal_release_timing.a4_verification_{name}"
                for name, passed in checks.items()
                if not passed
            )
    formal = _path(summary, "formal_release_timing", "p4")
    formal = formal if isinstance(formal, Mapping) else {}
    reported_checks = {
        "logical_matches_raw": formal.get("logical_p4_call_count") == all_totals["logical_units"],
        "mat_solve_matches_raw": formal.get("actual_mat_solve_count") == all_totals["actual_mat_solve"],
        "physical_matches_raw": formal.get("physical_f4_call_count") == all_totals["physical_f4_calls"],
    }
    failures.extend(
        f"formal_release_timing.{name}" for name, passed in reported_checks.items() if not passed
    )
    reported_pc_apply = _path(summary, "pc", "apply_count")
    expected_pc_apply = (setup_count or 0) + check_count + (iteration_count or 0)
    if reported_pc_apply != expected_pc_apply:
        failures.append("pc.apply_count_phase_closure")
    return {
        "status": "derived" if not failures else "failed",
        "passed": not failures and bool(rows),
        "failures": failures,
        "phase_counts": phase_totals,
        "setup_bal_h": setup_count,
        "check_bal_h": check_count,
        "iteration_bal_h": iteration_count,
        "total_bal_h": (setup_count or 0) + check_count + (iteration_count or 0),
        "raw_boundary_records": len(boundaries),
        "logical_units": all_totals["logical_units"],
        "nonzero_logical_units": all_totals["nonzero_logical_units"],
        "actual_mat_solve": all_totals["actual_mat_solve"],
        "physical_f4_calls": all_totals["physical_f4_calls"],
        "a4_action_count": all_totals["a4_action_count"],
        "a4_action_implementation": (
            sorted({row["a4_action_implementation"] for row in rows})
        ),
        "best_snapshot_peak_local_bytes": all_totals["best_snapshot_peak_local_bytes"],
        "selected_evidence_copy_local_bytes": all_totals[
            "selected_evidence_copy_local_bytes"
        ],
        "extra_repairs": all_totals["extra_repairs"],
        "coarse_target_met_all": coarse_target_met_all,
        "coarse_unmet_continued_count": coarse_unmet_continued_count,
        "returned_rho_distribution": {
            "count": len(returned),
            "min": returned[0] if returned else None,
            "p50": quantile(0.50),
            "p90": quantile(0.90),
            "p99": quantile(0.99),
            "max": returned[-1] if returned else None,
        },
        "reported_cross_checks": reported_checks,
        "rows": rows,
    }


def _residual_facts(summary: Mapping[str, Any]) -> dict[str, Any]:
    solver = summary.get("solver") if isinstance(summary.get("solver"), Mapping) else {}
    final = summary.get("final_explicit_relative_residual")
    if final is None:
        packet = summary.get("final_residual")
        final = packet.get("explicit_relative_residual") if isinstance(packet, Mapping) else None
    post = summary.get("post_release_explicit_relative_residual")
    if post is None:
        packet = summary.get("post_release_final_residual")
        post = packet.get("explicit_relative_residual") if isinstance(packet, Mapping) else None
    reported_true = solver.get("final_true_residual")
    # V25 always owns the post-KSP release boundary.  A missing/false flag is
    # a failed contract, not permission to skip the post-release A6 check.
    release_required = True
    checks = {
        "release_after_final_residual": summary.get("release_after_final_residual") is True,
        "solver_status": solver.get("status") == "TRUE_RESIDUAL_PASS",
        "reported_true_residual": _finite(reported_true) and float(reported_true) <= TRUE_RESIDUAL_LIMIT,
        "explicit_residual": _finite(final) and float(final) <= TRUE_RESIDUAL_LIMIT,
        "post_release_residual": _finite(post) and float(post) <= TRUE_RESIDUAL_LIMIT,
    }
    return {
        "status": "derived",
        "passed": all(checks.values()),
        "checks": checks,
        "reported_true_residual": reported_true,
        "explicit_residual": final,
        "post_release_explicit_residual": post,
        "release_required": release_required,
        "limit": TRUE_RESIDUAL_LIMIT,
    }


def _aq_facts(summary: Mapping[str, Any]) -> dict[str, Any]:
    aq = summary.get("native_aq_projection_check")
    if not isinstance(aq, Mapping):
        return {"status": "not_run", "passed": False, "reason": "native Aq check is absent"}
    volume = aq.get("volume") if isinstance(aq.get("volume"), Mapping) else {}
    dtn = aq.get("dtn") if isinstance(aq.get("dtn"), Mapping) else {}
    probe = aq.get("probe_identity") if isinstance(aq.get("probe_identity"), Mapping) else {}
    native_zero = aq.get("native_output_slave_zero")
    native_zero = native_zero if isinstance(native_zero, Mapping) else {}
    checks = {
        "reported_passed": aq.get("passed") is True,
        "owned_slave_zero": probe.get("owned_slave_zero") is True,
        "input_unchanged": probe.get("input_unchanged_after_transfer") is True,
        "volume_slave_zero": native_zero.get("volume") is True,
        "dtn_slave_zero": native_zero.get("dtn") is True,
        "volume_relative": _finite(volume.get("relative")) and float(volume["relative"]) <= NATIVE_AQ_LIMIT,
        "dtn_relative": _finite(dtn.get("relative")) and float(dtn["relative"]) <= NATIVE_AQ_LIMIT,
    }
    return {
        "status": "derived",
        "passed": all(checks.values()),
        "checks": checks,
        "volume_relative": volume.get("relative"),
        "dtn_relative": dtn.get("relative"),
        "limit": NATIVE_AQ_LIMIT,
    }


def _first_arnoldi_facts(summary: Mapping[str, Any], stage: str | None) -> dict[str, Any]:
    outer = _path(summary, "solver", "retained_outer")
    actual = outer.get("actual_first_arnoldi") if isinstance(outer, Mapping) else None
    if not isinstance(actual, Mapping):
        return {"status": "not_run", "passed": False, "reason": "actual first-Arnoldi record is absent"}
    pair = actual.get("pair")
    checks = {
        "reported_passed": actual.get("passed") is True,
        "input_is_zero_start_retained_rhs": actual.get("input_is_zero_start_retained_rhs") is True,
        "not_used_as_initial_guess": actual.get("used_as_initial_guess") is False,
        "finite_output": actual.get("finite_output") is True,
        "size_ok": actual.get("size_ok") is True,
    }
    if stage == "Q4_ORIGINAL":
        checks["four_variant_pair_passed"] = isinstance(pair, Mapping) and pair.get("passed") is True
    return {"status": "derived", "passed": all(checks.values()), "checks": checks}



def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _count_or_none(value: Any) -> int | None:
    try:
        return _number(value, "count")
    except ValueError:
        return None


def _runtime_thread_facts(environment: Mapping[str, Any] | None) -> dict[str, Any]:
    """Check recorded runtime thread values without treating absence as proof."""

    environment = environment if isinstance(environment, Mapping) else {}
    keys = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    present = {key: environment[key] for key in keys if key in environment}
    mismatches = {key: value for key, value in present.items() if str(value) != "1"}
    all_present = len(present) == len(keys)
    status = (
        "mismatch"
        if mismatches
        else "measured"
        if all_present
        else "EVIDENCE_LIMITED: runtime thread variables are incomplete"
    )
    return {
        "passed": not mismatches,
        "status": status,
        "values": present,
        "mismatches": mismatches,
    }


def _versioned_backend_facts(
    summary: Mapping[str, Any],
    resolved_config: Mapping[str, Any],
    stage: str | None,
    *,
    run_manifest: Mapping[str, Any] | None,
    resolved_config_sha256: str | None,
    raw_bal_h: Mapping[str, Any] | None,
) -> dict[str, Any]:
    solver = resolved_config.get("solver")
    if not isinstance(solver, Mapping):
        return {"status": "failed", "passed": False, "reason": "resolved config has no solver section"}
    profile = solver.get("preconditioner")
    expected_backend = BACKEND
    expected_h6 = "direct_selected_backend_same_apply_and_power10"
    expected_thread = "mpi1_omp1_blas1_v26"
    expected_degree = {"Q4_ORIGINAL": 4, "Q3_ORIGINAL": 3, "Q2_ORIGINAL": 2}.get(stage)

    release = summary.get("formal_release_timing")
    release = release if isinstance(release, Mapping) else {}
    candidate = release.get("candidate_pc_internal_A6")
    candidate = candidate if isinstance(candidate, Mapping) else {}
    live_candidate = candidate.get("live_audit")
    live_candidate = live_candidate if isinstance(live_candidate, Mapping) else {}
    volume = live_candidate.get("volume_action")
    volume = volume if isinstance(volume, Mapping) else {}
    components = volume.get("components")
    components = components if isinstance(components, Mapping) else {}

    component_checks: dict[str, dict[str, bool]] = {}
    quadrature_matches: dict[str, bool] = {}
    for name, component_name in (("curl_curl", "curl"), ("complex_material_mass", "mass")):
        component = components.get(name)
        component = component if isinstance(component, Mapping) else {}
        audit = component.get("sum_factorized_audit")
        audit = audit if isinstance(audit, Mapping) else {}
        shape = audit.get("quadrature_shape")
        coeff_shape = audit.get("coefficient_matrix_shape")
        component_checks[name] = {
            "backend": component.get("backend") == expected_backend,
            "component": component.get("component") == component_name,
            "sum_factorized_opt_in": component.get("sum_factorized_opt_in") is True,
            "element_identity": (
                audit.get("element_family") == "N1E"
                and audit.get("degree") == 6
                and audit.get("element_dimension") == 882
                and audit.get("element_variant") == "legendre"
                and audit.get("map_type") == "covariantPiola"
                and audit.get("polyset_type") == "standard"
                and coeff_shape == V30_V31_COMPONENT_IDENTITY["coefficient_matrix_shape"]
                and audit.get("backend") == expected_backend
            ),
            "coefficient_hash": _valid_sha256(audit.get("coefficient_matrix_sha256")),
            "quadrature_identity": (
                _positive_integer(component.get("quadrature_degree"))
                and isinstance(component.get("quadrature_rule"), str)
                and bool(component.get("quadrature_rule"))
                and _valid_sha256(component.get("points_sha256"))
                and _valid_sha256(component.get("weights_sha256"))
                and component.get("quadrature_degree") == V30_V31_COMPONENT_IDENTITY["quadrature_degree"]
                and component.get("quadrature_rule") == V30_V31_COMPONENT_IDENTITY["quadrature_rule"]
                and component.get("points") == V30_V31_COMPONENT_IDENTITY["points"]
                and component.get("points_sha256") == V30_V31_COMPONENT_IDENTITY["points_sha256"]
                and component.get("weights_sha256") == V30_V31_COMPONENT_IDENTITY["weights_sha256"]
                and audit.get("coefficient_matrix_sha256") == V30_V31_COMPONENT_IDENTITY["coefficient_matrix_sha256"]
                and audit.get("quadrature_weights_sha256") == V30_V31_COMPONENT_IDENTITY["weights_sha256"]
                and audit.get("quadrature_points") == V30_V31_COMPONENT_IDENTITY["points"]
                and audit.get("quadrature_order") == "actual_points_to_tensor_grid_checked"
                and shape == V30_V31_COMPONENT_IDENTITY["quadrature_shape"]
                and isinstance(shape, list)
                and len(shape) == 3
                and all(_positive_integer(value) for value in shape)
                and math.prod(shape) == component.get("points")
            ),
        }

    fused = volume.get("fused_local_kernel")
    fused = fused if isinstance(fused, Mapping) else {}
    fused_quadrature = fused.get("component_quadrature_identities")
    fused_quadrature = fused_quadrature if isinstance(fused_quadrature, Mapping) else {}
    for qname, component_name in (("curl", "curl_curl"), ("mass", "complex_material_mass")):
        component = components.get(component_name)
        component = component if isinstance(component, Mapping) else {}
        identity = fused_quadrature.get(qname)
        identity = identity if isinstance(identity, Mapping) else {}
        quadrature_matches[qname] = (
            identity.get("degree") == component.get("quadrature_degree")
            and identity.get("rule") == component.get("quadrature_rule")
            and identity.get("points_sha256") == component.get("points_sha256")
            and identity.get("weights_sha256") == component.get("weights_sha256")
            and _valid_sha256(identity.get("points_sha256"))
            and _valid_sha256(identity.get("weights_sha256"))
        )

    h6 = release.get("h6")
    h6 = h6 if isinstance(h6, Mapping) else {}
    h6_facts = h6.get("light_facts")
    h6_facts = h6_facts if isinstance(h6_facts, Mapping) else {}
    live_h6 = h6_facts.get("live_kernel_audit")
    live_h6 = live_h6 if isinstance(live_h6, Mapping) else {}
    h6_sum = live_h6.get("sum_factorized_audit")
    h6_sum = h6_sum if isinstance(h6_sum, Mapping) else {}
    h6_shape = h6_sum.get("quadrature_shape")
    h6_identity = (
        live_h6.get("backend") == expected_backend
        and live_h6.get("sum_factorized_opt_in") is True
        and live_h6.get("quadrature_degree") == V30_V31_COMPONENT_IDENTITY["quadrature_degree"]
        and live_h6.get("quadrature_rule") == V30_V31_COMPONENT_IDENTITY["quadrature_rule"]
        and live_h6.get("points") == V30_V31_COMPONENT_IDENTITY["points"]
        and live_h6.get("points_sha256") == V30_V31_COMPONENT_IDENTITY["points_sha256"]
        and live_h6.get("weights_sha256") == V30_V31_COMPONENT_IDENTITY["weights_sha256"]
        and h6_sum.get("backend") == expected_backend
        and h6_sum.get("degree") == 6
        and h6_sum.get("element_dimension") == 882
        and h6_sum.get("coefficient_matrix_shape") == V30_V31_COMPONENT_IDENTITY["coefficient_matrix_shape"]
        and h6_sum.get("coefficient_matrix_sha256") == V30_V31_COMPONENT_IDENTITY["coefficient_matrix_sha256"]
        and h6_sum.get("quadrature_weights_sha256") == V30_V31_COMPONENT_IDENTITY["weights_sha256"]
        and h6_sum.get("quadrature_points") == live_h6.get("points")
        and isinstance(h6_shape, list)
        and len(h6_shape) == 3
        and all(_positive_integer(value) for value in h6_shape)
        and math.prod(h6_shape) == live_h6.get("points")
    )

    pc = summary.get("pc")
    pc = pc if isinstance(pc, Mapping) else {}
    bal = release.get("BAL_H")
    bal = bal if isinstance(bal, Mapping) else {}
    bal_counts = bal.get("counts")
    bal_counts = bal_counts if isinstance(bal_counts, Mapping) else {}
    p4 = release.get("p4")
    p4 = p4 if isinstance(p4, Mapping) else {}
    a4 = release.get("a4_verification")
    a4 = a4 if isinstance(a4, Mapping) else {}
    pc_apply = _count_or_none(pc.get("apply_count"))
    logical_c = _count_or_none(p4.get("logical_p4_call_count"))
    mat_solves = _count_or_none(p4.get("actual_mat_solve_count"))
    physical_f4 = _count_or_none(p4.get("physical_f4_call_count"))
    a4_actions = _count_or_none(a4.get("action_count"))
    h6_apply = _count_or_none(h6.get("apply_count"))
    h6_top_apply = _count_or_none(release.get("h6_apply_count"))
    matrix_mults = _count_or_none(h6.get("matrix_mult_count"))
    power10_mults = _count_or_none(h6.get("power_matrix_mult_count"))
    facts_power10_mults = _count_or_none(h6_facts.get("power_matrix_mult_count"))
    candidate_apply = _count_or_none(live_candidate.get("apply_count"))
    fused_apply = _count_or_none(fused.get("apply_count"))
    fused_full_apply = _count_or_none(fused.get("full_apply_count"))
    volume_apply = _count_or_none(volume.get("apply_count"))

    checks: dict[str, bool] = {
        "profile_is_explicit_v30_or_v31": profile in VERSIONED_PROFILES,
        "physical_operator_backend": solver.get("physical_operator_backend") == expected_backend,
        "h6_backend_rule": solver.get("h6_backend_rule") == expected_h6,
        "thread_contract_declaration": solver.get("thread_contract") == expected_thread,
        "stage": stage is None or solver.get("stage") == stage,
        "coarse_degree": expected_degree is None or solver.get("coarse_degree") == expected_degree,
        "candidate_a6_live": bool(live_candidate),
        "candidate_a6_backend_and_component": all(
            item["backend"] and item["component"] for item in component_checks.values()
        ),
        "candidate_a6_element_and_coefficient_identity": all(
            item["element_identity"] and item["coefficient_hash"]
            for item in component_checks.values()
        ),
        "candidate_a6_quadrature_identity": all(
            item["quadrature_identity"] for item in component_checks.values()
        ),
        "candidate_a6_sum_factorized": all(
            item["sum_factorized_opt_in"] for item in component_checks.values()
        ),
        "fused_volume_schema": volume.get("schema") == "task039extra.fused-split-volume-action.v1",
        "fused_local_kernel_schema": fused.get("schema") == "task039extra.fused-isotropic-split-kernel.v1",
        "fused_quadrature_identity_matches_components": all(quadrature_matches.values()),
        "fused_integral_rules_preserved": fused.get("distinct_integral_rules_preserved") is True,
        "ordinary_default_unchanged": fused.get("ordinary_default_changed") is False,
        "fused_batch_and_apply_counts_close": _fused_batch_counts_close(volume, fused),
        "candidate_and_fused_full_apply_scope_matches": (
            candidate_apply is not None
            and candidate_apply == fused_apply == fused_full_apply == volume_apply
        ),
        "h6_apply_and_power10_backend": (
            h6_facts.get("apply_action_backend") == "packed_partial_assembly"
            and h6_facts.get("sum_factorized_work_opt_in") is True
            and h6_facts.get("power10_action_backend") == "packed_partial_assembly"
            and h6_facts.get("sum_factorized_power10_opt_in") is True
            and h6_facts.get("direct_selected_backend_used") is True
        ),
        "h6_live_kernel_identity": h6_identity,
        "h6_apply_count_scope_matches": (
            h6_apply is not None
            and h6_apply == h6_top_apply == pc.get("h6_apply_count")
            and h6_apply == pc_apply == _count_or_none(bal_counts.get("smoother"))
        ),
        "logical_C_count_scope_matches": (
            logical_c is not None
            and logical_c == _count_or_none(bal_counts.get("C"))
            and logical_c == _count_or_none(bal_counts.get("A_structure"))
            and pc_apply is not None
            and logical_c == 2 * pc_apply
        ),
        "actual_A4_mat_solve_scope_matches": (
            mat_solves is not None
            and mat_solves == physical_f4 == a4_actions
        ),
        "actual_B6_and_power10_scopes_close": (
            matrix_mults is not None
            and power10_mults is not None
            and logical_c is not None
            and matrix_mults == logical_c + power10_mults
            and power10_mults == 20
            and power10_mults == facts_power10_mults
        ),
    }
    call_scope = {
        "logical_C": logical_c,
        "actual_F4_MatSolve": mat_solves,
        "H6_apply": h6_apply,
        "B6_matrix_mult_including_power10": matrix_mults,
        "power10_B6": power10_mults,
        "legacy_calls_per_PC_template": {
            "value": h6_facts.get("calls_per_PC"),
            "authoritative": False,
            "note": "Historical metadata only; live C, H6, B6, MatSolve and power10 counters are checked by scope.",
        },
    }

    projection: dict[str, Any] | None = None
    if profile == V31_PROFILE:
        # V31 is a frozen H6-only profile. The resolved input schema binds the
        # choice through its profile identity; the checker compares that choice
        # to the live kernel audit instead of requiring unsupported ad hoc keys
        # in the .dat solver section.
        expected_natural = True
        expected_projection = False
        expected_scope = "h6"
        # V31's live execution audit records these opt-ins on the nested
        # sum-factorized kernel audit.  The parent live-kernel object carries
        # backend and quadrature identity, but not the projection-layout flags.
        h6_natural = h6_sum.get("natural_order_internal_opt_in")
        h6_projection = h6_sum.get("continuous_projection_matmul_opt_in")
        projection_checks = {
            "natural_order_flag_explicit": isinstance(expected_natural, bool),
            "continuous_projection_flag_explicit": isinstance(expected_projection, bool),
            "layout_flags_are_explicit": isinstance(expected_natural, bool) and isinstance(expected_projection, bool),
            "scope_explicit": expected_scope in {"h6", "shared_a6_h6"},
            "live_h6_flags_match_config": h6_natural is expected_natural and h6_projection is expected_projection,
            "projection_kernel_identity": (
                h6_sum.get("backward_projection_kernel") == "continuous_z_y_x_matmul_v31"
                if expected_projection is True
                else h6_sum.get("backward_projection_kernel") == "einsum_z_y_x_legacy"
            ),
            "source_tensor_grid_identity_preserved": (
                h6_sum.get("quadrature_order")
                == "actual_points_to_tensor_grid_checked"
                and h6_sum.get("points_sha256")
                == V30_V31_COMPONENT_IDENTITY["points_sha256"]
                and h6_sum.get("weights_sha256")
                == V30_V31_COMPONENT_IDENTITY["weights_sha256"]
            ),
            "natural_tensor_order_identity": (
                h6_sum.get("internal_quadrature_order")
                == "natural_tensor_order_v31"
                if expected_natural is True
                else h6_sum.get("internal_quadrature_order")
                == "source_input_order"
            ),
            "point_weight_permutation_identity": (
                _valid_sha256(h6_sum.get("internal_points_sha256"))
                and _valid_sha256(h6_sum.get("internal_weights_sha256"))
                and h6_sum.get("point_permutation_bijection_verified") is True
                and h6_sum.get("weights_permuted_with_points") is expected_natural
            ),
            "projection_workspace_is_bounded": (
                _positive_integer(h6_sum.get("projection_workspace_bytes"))
                if expected_projection is True
                else h6_sum.get("projection_workspace_bytes") == 0
            ),
        }
        if expected_scope == "shared_a6_h6":
            projection_checks["a6_flags_match_shared_scope"] = all(
                isinstance(components.get(name), Mapping)
                and components[name].get("natural_order_internal_opt_in") is expected_natural
                and components[name].get("continuous_projection_matmul_opt_in") is expected_projection
                for name in ("curl_curl", "complex_material_mass")
            )
        elif expected_scope == "h6":
            def a6_layout_unchanged(name: str) -> bool:
                component = components.get(name)
                if not isinstance(component, Mapping):
                    return False
                audit = component.get("sum_factorized_audit")
                audit = audit if isinstance(audit, Mapping) else {}
                layout = audit.get("projection_layout_v31_candidate")
                layout = layout if isinstance(layout, Mapping) else {}
                return (
                    layout.get("natural_order_internal") is False
                    and layout.get("continuous_projection_matmul") is False
                )

            projection_checks["a6_unchanged_for_h6_scope"] = all(
                a6_layout_unchanged(name)
                for name in ("curl_curl", "complex_material_mass")
            )
        else:
            projection_checks["a6_scope_invalid"] = False
        checks["v31_projection_layout_contract"] = all(projection_checks.values())
        projection = {
            "status": "derived",
            "passed": all(projection_checks.values()),
            "checks": projection_checks,
        }

    manifest = run_manifest if isinstance(run_manifest, Mapping) else {}
    manifest_env = manifest.get("environment")
    manifest_env = manifest_env if isinstance(manifest_env, Mapping) else {}
    runtime_threads = _runtime_thread_facts(manifest_env)
    checks["runtime_thread_environment_matches_one"] = runtime_threads["passed"]
    raw_bal = raw_bal_h if isinstance(raw_bal_h, Mapping) else {}
    raw_setup = _count_or_none(raw_bal.get("setup_bal_h"))
    raw_check = _count_or_none(raw_bal.get("check_bal_h"))
    raw_outer = _count_or_none(raw_bal.get("iteration_bal_h"))
    raw_total = _count_or_none(raw_bal.get("total_bal_h"))
    raw_boundaries = _count_or_none(raw_bal.get("raw_boundary_records"))
    raw_logical_c = _count_or_none(raw_bal.get("logical_units"))
    solver_outer = _count_or_none(_path(summary, "solver", "pc_apply_count"))
    checks["raw_bal_h_phase_and_pc_scope_closure"] = (
        raw_bal.get("passed") is True
        and raw_setup == 1
        and raw_check == 4
        and raw_outer is not None
        and raw_outer == solver_outer
        and raw_total == raw_setup + raw_check + raw_outer
        and raw_boundaries == raw_total
        and pc_apply == raw_total
        and h6_apply == pc_apply
        and raw_logical_c == logical_c == 2 * raw_total
    )
    checks["resolved_config_hash_matches_manifest"] = (
        run_manifest is not None
        and resolved_config_sha256 is not None
        and manifest.get("resolved_config_sha256") == resolved_config_sha256
    )
    return {
        "status": "derived",
        "passed": all(checks.values()),
        "checks": checks,
        "candidate_component_checks": component_checks,
        "quadrature_identity_matches": quadrature_matches,
        "call_scope": call_scope,
        "projection_layout": projection,
        "runtime_thread_evidence": runtime_threads["status"],
        "runtime_thread_values": runtime_threads["values"],
        "raw_pc_scope": {
            "setup_BAL_H": raw_setup,
            "check_BAL_H": raw_check,
            "outer_iteration_BAL_H": raw_outer,
            "cumulative_PC_apply": raw_total,
            "raw_boundary_records": raw_boundaries,
            "logical_C": raw_logical_c,
        },
    }


def _monitoring_facts(
    run_manifest: Mapping[str, Any] | None,
    run_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    manifest = run_manifest if isinstance(run_manifest, Mapping) else {}
    summary = run_summary if isinstance(run_summary, Mapping) else {}
    environment = manifest.get("environment")
    environment = environment if isinstance(environment, Mapping) else {}
    authority = summary.get("resource_authority")
    authority = authority if isinstance(authority, Mapping) else {}
    source_state = authority.get("source_state")
    source_state = source_state if isinstance(source_state, Mapping) else {}
    pss_peak = authority.get("sampled_process_tree_pss_peak_bytes")
    pss_status = authority.get("pss_status")
    # V30/V31 explicitly disabled PSS to avoid an expensive per-sample scan.
    # A positive PSS value here would indicate a changed monitoring profile.
    pss_ok = pss_status == "DISABLED_BY_PROFILE" and pss_peak is None
    pss_interpretation = "explicitly_disabled_not_zero" if pss_ok else "profile_mismatch"
    runtime_threads = _runtime_thread_facts(environment)
    swap_peak = _count_or_none(authority.get("sampled_process_tree_swap_peak_bytes"))
    checks = {
        "manifest_mpi1": manifest.get("mpi_size") == 1,
        "manifest_qualified_linux_environment": (
            environment.get("qualified_activation") == "1"
            and isinstance(environment.get("platform"), str)
            and "linux" in environment.get("platform", "").lower()
            and isinstance(environment.get("python_executable"), str)
            and ".venv" in environment.get("python_executable", "")
        ),
        "run_finished_exit0": summary.get("status") == "finished" and summary.get("exit_status") == 0,
        "watchdog_completed": authority.get("classification") == "COMPLETED",
        "watchdog_leader_exit0": authority.get("leader_exit_code") == 0,
        "watchdog_descendants_cleared": (
            authority.get("descendants_cleared") is True
            and authority.get("remaining_child_pids") == []
        ),
        "rss_peak_recorded": _positive_integer(authority.get("sampled_process_tree_rss_peak_bytes")),
        "swap_observed_only": (
            summary.get("swap_policy") == "observe_only"
            and authority.get("swap_policy") == "observe_only"
            and authority.get("process_tree_swap_gate_enforced") is False
            and swap_peak is not None
        ),
        "pss_status_explicit_and_disabled_by_profile": pss_ok,
        "runtime_thread_environment_matches_one": runtime_threads["passed"],
        "source_identity_matches_manifest": (
            isinstance(manifest.get("source_sha"), str)
            and manifest.get("source_sha") == source_state.get("source_sha")
            and source_state.get("tracked_and_nonignored_untracked_clean") is True
        ),
    }
    return {
        "status": "derived",
        "passed": all(checks.values()),
        "checks": checks,
        "pss_interpretation": pss_interpretation,
        "swap_interpretation": "observed_only_not_enforced",
        "thread_runtime_evidence": runtime_threads["status"],
        "thread_runtime_values": runtime_threads["values"],
        "sampled_rss_peak_bytes": authority.get("sampled_process_tree_rss_peak_bytes"),
        "sampled_swap_peak_bytes": authority.get("sampled_process_tree_swap_peak_bytes"),
    }


def _backend_facts(
    summary: Mapping[str, Any],
    resolved_config: Mapping[str, Any] | None,
    stage: str | None,
    *,
    run_manifest: Mapping[str, Any] | None = None,
    resolved_config_sha256: str | None = None,
    raw_bal_h: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if resolved_config is None:
        return {"status": "not_run", "passed": False, "reason": "resolved config was not supplied"}
    solver = resolved_config.get("solver")
    if not isinstance(solver, Mapping):
        return {"status": "failed", "passed": False, "reason": "resolved config has no solver section"}
    if solver.get("preconditioner") in VERSIONED_PROFILES:
        return _versioned_backend_facts(
            summary,
            resolved_config,
            stage,
            run_manifest=run_manifest,
            resolved_config_sha256=resolved_config_sha256,
            raw_bal_h=raw_bal_h,
        )
    workingset_profile = (
        solver.get("preconditioner")
        == "physical_p6_trace_workingset_efficiency_v27"
    )
    fused_kernel_profile = (
        solver.get("preconditioner")
        == "physical_p6_trace_fused_kernel_v28"
    )
    best_finite_profile = (
        solver.get("preconditioner") == BEST_FINITE_EXHAUSTION_PROFILE
    )
    fused_kernel_profile = fused_kernel_profile or best_finite_profile
    expected_h6_backend = (
        "direct_selected_backend_same_apply_and_power10"
        if workingset_profile or fused_kernel_profile
        else H6_BACKEND
    )
    expected_thread_contract = (
        "mpi1_omp1_blas1_v26"
        if workingset_profile or fused_kernel_profile
        else THREAD_CONTRACT
    )
    expected_degree = {"Q4_ORIGINAL": 4, "Q3_ORIGINAL": 3, "Q2_ORIGINAL": 2}.get(stage)
    release = summary.get("formal_release_timing")
    release = release if isinstance(release, Mapping) else {}
    candidate = release.get("candidate_pc_internal_A6")
    candidate = candidate if isinstance(candidate, Mapping) else {}
    live_candidate = candidate.get("live_audit")
    live_candidate = live_candidate if isinstance(live_candidate, Mapping) else {}
    volume_action = live_candidate.get("volume_action")
    volume_action = volume_action if isinstance(volume_action, Mapping) else {}
    components = volume_action.get("components")
    components = components if isinstance(components, Mapping) else {}
    component_checks: dict[str, dict[str, bool]] = {}
    for name in ("curl_curl", "complex_material_mass"):
        component = components.get(name)
        component = component if isinstance(component, Mapping) else {}
        kernel = (
            component
            if fused_kernel_profile
            else component.get("local_kernel")
        )
        kernel = kernel if isinstance(kernel, Mapping) else {}
        component_checks[name] = {
            "backend": kernel.get("backend") == BACKEND,
            "sum_factorized_opt_in": kernel.get("sum_factorized_opt_in") is True,
            "apply_count": (
                True
                if fused_kernel_profile
                else _positive_integer(component.get("apply_count"))
            ),
            "shared_contractions_opt_in": (
                kernel.get("shared_contractions_opt_in") is False
                if fused_kernel_profile
                else True
            ),
        }
    live_h6 = release.get("h6")
    live_h6 = live_h6 if isinstance(live_h6, Mapping) else {}
    live_h6_facts = live_h6.get("light_facts")
    live_h6_facts = live_h6_facts if isinstance(live_h6_facts, Mapping) else {}
    h6_live_kernel = live_h6_facts.get("live_kernel_audit")
    h6_live_kernel = h6_live_kernel if isinstance(h6_live_kernel, Mapping) else {}
    fused_volume = volume_action.get("fused_local_kernel")
    fused_volume = fused_volume if isinstance(fused_volume, Mapping) else {}
    tensor_contractions = fused_volume.get("tensor_contractions")
    tensor_contractions = (
        tensor_contractions if isinstance(tensor_contractions, Mapping) else {}
    )
    fused_curl = tensor_contractions.get("curl")
    fused_curl = fused_curl if isinstance(fused_curl, Mapping) else {}
    fused_mass = tensor_contractions.get("mass")
    fused_mass = fused_mass if isinstance(fused_mass, Mapping) else {}
    h6_sum_factorized = h6_live_kernel.get("sum_factorized_audit")
    h6_sum_factorized = (
        h6_sum_factorized if isinstance(h6_sum_factorized, Mapping) else {}
    )
    h6_timing = h6_live_kernel.get("timing_cumulative_seconds")
    h6_timing = h6_timing if isinstance(h6_timing, Mapping) else {}
    candidate_apply_count = live_candidate.get("apply_count")
    h6_apply_count = live_h6.get("apply_count")
    h6_top_apply_count = release.get("h6_apply_count")
    h6_pc_apply_count = _path(summary, "pc", "h6_apply_count")
    checks = {
        "physical_operator_backend": solver.get("physical_operator_backend") == BACKEND,
        "h6_backend_rule": solver.get("h6_backend_rule") == expected_h6_backend,
        "thread_contract": solver.get("thread_contract") == expected_thread_contract,
        "stage": stage is None or solver.get("stage") == stage,
        "coarse_degree": expected_degree is None or solver.get("coarse_degree") == expected_degree,
        "live_candidate_a6_present": bool(live_candidate),
        "live_candidate_a6_backend": all(item["backend"] for item in component_checks.values()),
        "live_candidate_a6_apply_count": _positive_integer(candidate_apply_count),
        "candidate_sum_factorized": all(
            item["sum_factorized_opt_in"] for item in component_checks.values()
        ),
        "candidate_curl_component_applied": component_checks["curl_curl"]["apply_count"],
        "candidate_mass_component_applied": component_checks["complex_material_mass"]["apply_count"],
        # These facts are read from the formal release snapshot, after the
        # live H6 object has actually applied.  pc.h6_facts is retained only
        # as a secondary report and is not the backend authority.
        "h6_release_apply_count": _positive_integer(h6_apply_count),
        "h6_release_count_matches_top_level": h6_top_apply_count == h6_apply_count,
        "h6_release_count_matches_pc": h6_pc_apply_count == h6_apply_count,
        "h6_release_count_matches_total_pc": _path(summary, "pc", "apply_count")
        == h6_apply_count,
        "h6_apply_sum_factorized": live_h6_facts.get("apply_action_backend")
        == "packed_partial_assembly"
        and live_h6_facts.get("sum_factorized_work_opt_in") is True,
        "h6_power10_sum_factorized": live_h6_facts.get("power10_action_backend")
        == "packed_partial_assembly"
        and live_h6_facts.get("sum_factorized_power10_opt_in") is True,
        "fused_volume_schema": (
            volume_action.get("schema")
            == "task039extra.fused-split-volume-action.v1"
            if fused_kernel_profile
            else True
        ),
        "fused_curl_and_mass_integrated": (
            _positive_integer(fused_volume.get("curl_integral_count"))
            and _positive_integer(fused_volume.get("mass_integral_count"))
            if fused_kernel_profile
            else True
        ),
        "fused_batch_and_apply_counts_close": (
            _fused_batch_counts_close(volume_action, fused_volume)
            if fused_kernel_profile
            else True
        ),
        "candidate_a6_shared_contractions_disabled": (
            all(
                item["shared_contractions_opt_in"]
                for item in component_checks.values()
            )
            if fused_kernel_profile
            else True
        ),
        "candidate_a6_contraction_audit_present": (
            _positive_integer(
                fused_curl.get("forward_tensor_contraction_count")
            )
            and _positive_integer(
                fused_curl.get("backward_tensor_contraction_count")
            )
            and _positive_integer(
                fused_mass.get("forward_tensor_contraction_count")
            )
            and _positive_integer(
                fused_mass.get("backward_tensor_contraction_count")
            )
            and _positive_number(
                _path(
                    fused_curl,
                    "timing_cumulative_seconds",
                    "reference_forward",
                )
            )
            and _positive_number(
                _path(
                    fused_curl,
                    "timing_cumulative_seconds",
                    "reference_backward",
                )
            )
            and _positive_number(
                _path(
                    fused_mass,
                    "timing_cumulative_seconds",
                    "reference_forward",
                )
            )
            and _positive_number(
                _path(
                    fused_mass,
                    "timing_cumulative_seconds",
                    "reference_backward",
                )
            )
            if fused_kernel_profile
            else True
        ),
        "h6_apply_shared_contractions_disabled": (
            h6_live_kernel.get("shared_contractions_opt_in") is False
            and _positive_integer(
                h6_sum_factorized.get("forward_tensor_contraction_count")
            )
            and _positive_integer(
                h6_sum_factorized.get("backward_tensor_contraction_count")
            )
            and _positive_number(h6_timing.get("reference_forward"))
            and _positive_number(h6_timing.get("reference_backward"))
            if fused_kernel_profile
            else True
        ),
        "h6_power10_uses_same_live_nonshared_backend": (
            live_h6_facts.get("direct_selected_backend_used") is True
            and live_h6_facts.get("apply_action_backend")
            == "packed_partial_assembly"
            and live_h6_facts.get("power10_action_backend")
            == "packed_partial_assembly"
            and live_h6_facts.get("sum_factorized_power10_opt_in") is True
            and _positive_integer(live_h6_facts.get("power_matrix_mult_count"))
            and _positive_number(live_h6_facts.get("power_matrix_mult_seconds"))
            and h6_live_kernel.get("shared_contractions_opt_in") is False
            and _positive_integer(
                h6_sum_factorized.get("forward_tensor_contraction_count")
            )
            and _positive_integer(
                h6_sum_factorized.get("backward_tensor_contraction_count")
            )
            and _positive_number(h6_timing.get("reference_forward"))
            and _positive_number(h6_timing.get("reference_backward"))
            if fused_kernel_profile
            else True
        ),
    }
    return {
        "status": "derived",
        "passed": all(checks.values()),
        "checks": checks,
        "candidate_component_checks": component_checks,
    }


def check_summary(
    summary: Mapping[str, Any],
    *,
    resolved_config: Mapping[str, Any] | None = None,
    stage: str | None = None,
    run_manifest: Mapping[str, Any] | None = None,
    run_summary: Mapping[str, Any] | None = None,
    resolved_config_sha256: str | None = None,
) -> dict[str, Any]:
    """Return only the dynamic accounting/wiring audit."""

    solver_config = (
        resolved_config.get("solver")
        if isinstance(resolved_config, Mapping)
        and isinstance(resolved_config.get("solver"), Mapping)
        else {}
    )
    allow_soft_return = solver_config.get("preconditioner") in (
        {BEST_FINITE_EXHAUSTION_PROFILE} | VERSIONED_PROFILES
    )
    bal_h = _raw_bal_h_facts(
        summary, stage, allow_soft_return=allow_soft_return
    )
    residual = _residual_facts(summary)
    aq = _aq_facts(summary)
    arnoldi = _first_arnoldi_facts(summary, stage)
    backend = _backend_facts(
        summary,
        resolved_config,
        stage,
        run_manifest=run_manifest,
        resolved_config_sha256=resolved_config_sha256,
        raw_bal_h=bal_h,
    )
    versioned = (
        isinstance(solver_config, Mapping)
        and solver_config.get("preconditioner") in VERSIONED_PROFILES
    )
    monitoring = (
        _monitoring_facts(run_manifest, run_summary)
        if versioned
        else {"status": "not_applicable", "passed": True, "checks": {}}
    )
    dynamic_gates = {
        "raw_bal_h_and_p4": bal_h["passed"],
        "true_residual": residual["passed"],
        "native_aq": aq["passed"],
        "actual_first_arnoldi": arnoldi["passed"],
        "backend_identity": backend["passed"],
    }
    if versioned:
        dynamic_gates["run_monitoring_identity"] = monitoring["passed"]
    dynamic_failures = [name for name, passed in dynamic_gates.items() if not passed]
    evidence_limited = versioned and (
        str(backend.get("runtime_thread_evidence", "")).startswith("EVIDENCE_LIMITED")
        or str(monitoring.get("thread_runtime_evidence", "")).startswith("EVIDENCE_LIMITED")
    )
    dynamic_status = (
        "DYNAMIC_FAIL"
        if dynamic_failures
        else "DYNAMIC_PASS_EVIDENCE_LIMITED"
        if evidence_limited
        else "DYNAMIC_PASS"
    )
    return {
        "schema": VERSIONED_CHECKER_SCHEMA if versioned else CHECKER_SCHEMA,
        "scope": "dynamic_accounting_and_wiring_only",
        "status": dynamic_status,
        "partial": True,
        "dynamic_passed": not dynamic_failures,
        "gate_failures": dynamic_failures,
        "worker_status_observed": summary.get("status"),
        "recomputed": {
            "bal_h_and_p4": bal_h,
            "residual": residual,
            "native_aq": aq,
            "actual_first_arnoldi": arnoldi,
            "backend": backend,
            "monitoring": monitoring,
        },
        "gates": dynamic_gates,
    }


def _read(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("--resolved-config", type=Path)
    parser.add_argument("--run-manifest", type=Path)
    parser.add_argument("--run-summary", type=Path)
    parser.add_argument("--stage")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    config_sha256 = (
        __import__("hashlib").sha256(args.resolved_config.read_bytes()).hexdigest()
        if args.resolved_config
        else None
    )
    result = check_summary(
        _read(args.summary),
        resolved_config=_read(args.resolved_config) if args.resolved_config else None,
        run_manifest=_read(args.run_manifest) if args.run_manifest else None,
        run_summary=_read(args.run_summary) if args.run_summary else None,
        resolved_config_sha256=config_sha256,
        stage=args.stage,
    )
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if result["dynamic_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
