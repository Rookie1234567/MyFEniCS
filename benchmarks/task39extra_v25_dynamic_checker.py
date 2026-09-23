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
TRUE_RESIDUAL_LIMIT = 1.0e-6
NATIVE_AQ_LIMIT = 1.0e-10

BACKEND = "isotropic_sum_factorized_n1e_v26"
H6_BACKEND = "isotropic_sum_factorized_n1e_v26_apply_and_power10"
THREAD_CONTRACT = "mpi1_omp1_blas1_v25"


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


def _raw_call_facts(call: Any, label: str) -> tuple[dict[str, Any], list[str]]:
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
    final_ratio = residual_rows[-1]["recomputed_relative"] if residual_rows else math.nan
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
        "extra_repairs": max(extra, 0),
        "repair_records": len(records),
        "residuals": residual_rows,
        "final_recomputed_relative": final_ratio,
    }, failures


def _raw_bal_h_facts(summary: Mapping[str, Any], stage: str | None = None) -> dict[str, Any]:
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
            facts, call_failures = _raw_call_facts(call, f"boundary[{index}].call[{call_index}]")
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
            "extra_repairs": sum(int(row["extra_repairs"]) for row in items),
        }

    phase_totals = {phase: totals(phase_rows[phase]) for phase in phase_names}
    all_totals = totals(rows)
    if all_totals["actual_mat_solve"] != (
        all_totals["nonzero_logical_units"] + all_totals["extra_repairs"]
    ):
        failures.append("mat_solve_nonzero_logical_plus_repairs_mismatch")
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
        "extra_repairs": all_totals["extra_repairs"],
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


def _backend_facts(
    summary: Mapping[str, Any], resolved_config: Mapping[str, Any] | None, stage: str | None
) -> dict[str, Any]:
    if resolved_config is None:
        return {"status": "not_run", "passed": False, "reason": "resolved config was not supplied"}
    solver = resolved_config.get("solver")
    if not isinstance(solver, Mapping):
        return {"status": "failed", "passed": False, "reason": "resolved config has no solver section"}
    workingset_profile = (
        solver.get("preconditioner")
        == "physical_p6_trace_workingset_efficiency_v27"
    )
    expected_h6_backend = (
        "direct_selected_backend_same_apply_and_power10"
        if workingset_profile
        else H6_BACKEND
    )
    expected_thread_contract = (
        "mpi1_omp1_blas1_v26" if workingset_profile else THREAD_CONTRACT
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
        kernel = component.get("local_kernel")
        kernel = kernel if isinstance(kernel, Mapping) else {}
        component_checks[name] = {
            "backend": kernel.get("backend") == BACKEND,
            "sum_factorized_opt_in": kernel.get("sum_factorized_opt_in") is True,
            "apply_count": _positive_integer(component.get("apply_count")),
        }
    live_h6 = release.get("h6")
    live_h6 = live_h6 if isinstance(live_h6, Mapping) else {}
    live_h6_facts = live_h6.get("light_facts")
    live_h6_facts = live_h6_facts if isinstance(live_h6_facts, Mapping) else {}
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
) -> dict[str, Any]:
    """Return only the dynamic accounting/wiring audit."""

    bal_h = _raw_bal_h_facts(summary, stage)
    residual = _residual_facts(summary)
    aq = _aq_facts(summary)
    arnoldi = _first_arnoldi_facts(summary, stage)
    backend = _backend_facts(summary, resolved_config, stage)
    dynamic_gates = {
        "raw_bal_h_and_p4": bal_h["passed"],
        "true_residual": residual["passed"],
        "native_aq": aq["passed"],
        "actual_first_arnoldi": arnoldi["passed"],
        "backend_identity": backend["passed"],
    }
    dynamic_failures = [name for name, passed in dynamic_gates.items() if not passed]
    return {
        "schema": CHECKER_SCHEMA,
        "scope": "dynamic_accounting_and_wiring_only",
        "status": "DYNAMIC_PASS" if not dynamic_failures else "DYNAMIC_FAIL",
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
    parser.add_argument("--stage")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check_summary(
        _read(args.summary),
        resolved_config=_read(args.resolved_config) if args.resolved_config else None,
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
