"""Independently check hash-bound V14 saved same-LU RHS candidate evidence."""

from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from src.runners.task41_p0_contract import (
    TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE,
    load_task41_p0_fixed_window,
    require_task41_p0_contract,
    sha256_file,
)
from src.runners.task41_p0_v14_candidate_io import (
    V14_CANDIDATE_CHECK_SCHEMA,
    V14_CANDIDATE_REPORT_SCHEMA,
    V14_SOURCE_WINDOW_SHA256,
    V14_CELLS,
    V14_COLUMNS,
    load_v14_saved_candidate_inputs,
)
from src.runners.task41_p0_v4_volume_only_audit import (
    TASK41_P0_V11_METADATA_ACTIVE_ROW,
)

V14_EXPECTED_INTERNAL_ROWS = 450


def _pair(value: Any, label: str) -> complex:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"V14 {label} is not a serialized complex pair")
    result = complex(float(value[0]), float(value[1]))
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise ValueError(f"V14 {label} is non-finite")
    return result


def _path_inside(path_value: Any, root: Path, label: str) -> Path:
    if not isinstance(path_value, str) or not path_value:
        raise ValueError(f"V14 {label} path is missing")
    path = Path(path_value).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError(f"V14 {label} escaped its candidate package")
    return path


def _load_array_ref(ref: Any, *, package: Path, label: str) -> np.ndarray:
    if not isinstance(ref, Mapping):
        raise ValueError(f"V14 {label} reference is malformed")
    path = _path_inside(ref.get("path"), package, label)
    if (
        path.stat().st_size != ref.get("bytes")
        or sha256_file(path) != ref.get("sha256")
    ):
        raise ValueError(f"V14 {label} path/size/hash differs")
    value = np.load(path, allow_pickle=False)
    if (
        list(value.shape) != ref.get("shape")
        or str(value.dtype) != ref.get("dtype")
        or value.dtype != np.dtype(np.complex128)
        or not np.isfinite(value).all()
    ):
        raise ValueError(f"V14 {label} dtype/shape/finiteness differs")
    return np.asarray(value)


def _load_event_log(ref: Any, *, package: Path, label: str) -> list[dict[str, Any]]:
    if not isinstance(ref, Mapping):
        raise ValueError(f"V14 {label} event log reference is malformed")
    path = _path_inside(ref.get("path"), package, f"{label}/event_log")
    if path.stat().st_size != ref.get("bytes") or sha256_file(path) != ref.get("sha256"):
        raise ValueError(f"V14 {label} event log path/size/hash differs")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"V14 {label} event {line_number} is not an object")
            records.append(record)
    return records


def _wide_residual(
    matrix: np.ndarray, rhs: np.ndarray, state: np.ndarray
) -> tuple[np.ndarray, dict[str, float], np.ndarray]:
    if matrix.shape != (V14_EXPECTED_INTERNAL_ROWS, V14_EXPECTED_INTERNAL_ROWS):
        raise ValueError("V14 initial-screen source matrix is not the frozen 450-row K")
    if rhs.shape != (V14_EXPECTED_INTERNAL_ROWS,) or state.shape != rhs.shape:
        raise ValueError("V14 initial-screen RHS/state is not the frozen 450-row layout")
    wide_matrix = np.asarray(matrix, dtype=np.clongdouble)
    wide_rhs = np.asarray(rhs, dtype=np.clongdouble)
    wide_state = np.asarray(state, dtype=np.clongdouble)
    residual = wide_rhs - wide_matrix @ wide_state
    abs_matrix = np.abs(wide_matrix)
    abs_state = np.abs(wide_state)
    row_scale = np.abs(wide_rhs) + abs_matrix @ abs_state
    tiny = np.finfo(np.longdouble).tiny
    row_roundoff = (
        np.longdouble(64 * V14_EXPECTED_INTERNAL_ROWS)
        * np.finfo(np.longdouble).eps
        * np.maximum(row_scale, tiny)
    )
    abs_residual = np.abs(residual)
    norm2 = np.sqrt(np.sum(abs_residual * abs_residual, dtype=np.longdouble))
    rhs_norm2 = np.sqrt(np.sum(np.abs(wide_rhs) ** 2, dtype=np.longdouble))
    resolution = np.sqrt(np.sum(row_roundoff * row_roundoff, dtype=np.longdouble))
    denominator = np.maximum(row_scale, tiny)
    metrics = {
        "absolute_l2": float(norm2),
        "absolute_inf": float(np.max(abs_residual)),
        "relative_rhs_l2": float(norm2 / max(rhs_norm2, tiny)),
        "componentwise_backward_error": float(np.max(abs_residual / denominator)),
        "wide_evaluation_resolution_l2": float(resolution),
    }
    if not all(math.isfinite(value) for value in metrics.values()):
        raise ValueError("V14 independent wide residual metrics are non-finite")
    return residual, metrics, row_scale


def _close_to_wide(
    actual: np.ndarray, expected: np.ndarray, scale: np.ndarray, *, label: str
) -> float:
    if actual.shape != expected.shape:
        raise ValueError(f"V14 {label} shape differs from the independent result")
    actual_wide = np.asarray(actual, dtype=np.clongdouble)
    expected_wide = np.asarray(expected, dtype=np.clongdouble)
    scale_wide = np.asarray(scale, dtype=np.longdouble)
    allowance = (
        np.longdouble(64 * max(1, actual.size))
        * np.finfo(np.float64).eps
        * np.maximum(scale_wide, np.finfo(np.longdouble).tiny)
    )
    difference = np.abs(actual_wide - expected_wide)
    if np.any(difference > allowance):
        raise ValueError(f"V14 {label} differs from the independent wide result")
    return float(np.max(difference))


def _identity_token(source: Mapping[str, Any], cell: int) -> str:
    import hashlib

    identity = {
        "producer_report_sha256": source["producer_report_sha256"],
        "cell_index": int(cell),
        "actual_coordinate_sha256": source["cells"][cell]["actual_coordinate_sha256"],
        "oriented_tensor_sha256": source["cells"][cell]["tensor_ref"]["sha256"],
        "interior_lu_sha256": source["cells"][cell]["lu_ref"]["sha256"],
    }
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


def _check_rhs(
    *, source: Mapping[str, Any], package: Path, record: Mapping[str, Any]
) -> dict[str, Any]:
    cell = int(record.get("cell_index", -1))
    column = int(record.get("column", -1))
    if cell not in V14_CELLS or column not in V14_COLUMNS:
        raise ValueError("V14 candidate contains an out-of-scope cell/column")
    local = source["cells"][cell]
    term = local["column_terms"][column]
    if (
        record.get("matrix_identity") != _identity_token(source, cell)
        or record.get("actual_coordinate_sha256") != local["actual_coordinate_sha256"]
        or record.get("oriented_tensor") != local["tensor_ref"]
        or record.get("interior_lu") != local["lu_ref"]
        or record.get("b_i") != term["b_i_ref"]
    ):
        raise ValueError(f"V14 cell{cell}/column{column} source identity differs")

    if record.get("old_z_b") != term["old_z_b_ref"]:
        raise ValueError(f"V14 cell{cell}/column{column} saved initial z_b identity differs")
    events = _load_event_log(
        record.get("initial_and_step_log"), package=package,
        label=f"cell{cell}/column{column}",
    )
    if (
        len(events) < 2
        or events[0].get("event") != "initial"
        or events[-1].get("event") != "final"
        or sum(item.get("event") == "initial" for item in events) != 1
        or sum(item.get("event") == "final" for item in events) != 1
        or any(item.get("event") != "correction_step" for item in events[1:-1])
        or [item.get("step") for item in events[1:-1]] != list(range(1, len(events) - 1))
        or len(events[1:-1]) > 2
    ):
        raise ValueError(f"V14 cell{cell}/column{column} callback sequence is not initial/correction*/final")
    matrix = local["K"]
    rhs = term["b_i"]
    state = _load_array_ref(events[0].get("solved"), package=package, label=f"cell{cell}/column{column}/initial_z")
    if state.shape != rhs.shape:
        raise ValueError(f"V14 cell{cell}/column{column} initial state shape differs")
    residual_rows: list[dict[str, Any]] = []
    residual, initial_metrics, row_scale = _wide_residual(matrix, rhs, state)
    residual_rows.append({"state": "initial", **initial_metrics})
    if not np.array_equal(state, term["old_z_b"]):
        raise ValueError(f"V14 cell{cell}/column{column} initial z0 differs from frozen saved z_b")
    current_state = np.asarray(state, dtype=np.complex128)
    getrs_count = int(events[0].get("initial_getrs_count", -1))
    if getrs_count != 1 or int(events[0].get("getrs_count", -1)) != 1:
        raise ValueError(f"V14 cell{cell}/column{column} initial GETRS accounting differs")
    correction_count = 0
    for index, event in enumerate(events[1:-1], 1):
        z_before = _load_array_ref(event.get("z_before"), package=package, label=f"cell{cell}/column{column}/step{index}/z_before")
        if not np.array_equal(z_before, current_state):
            raise ValueError(f"V14 cell{cell}/column{column} step{index} z_before breaks the saved chain")
        independent_residual, step_metrics, row_scale = _wide_residual(matrix, rhs, z_before)
        saved_residual = _load_array_ref(event.get("residual"), package=package, label=f"cell{cell}/column{column}/step{index}/residual")
        _close_to_wide(
            saved_residual, independent_residual, row_scale,
            label=f"cell{cell}/column{column}/step{index} production residual",
        )
        residual_rows.append({"state": f"before_correction_{index}", **step_metrics})
        delta_ref = event.get("delta")
        z_after = _load_array_ref(event.get("z_after"), package=package, label=f"cell{cell}/column{column}/step{index}/z_after")
        if delta_ref is None:
            if not np.array_equal(z_after, z_before):
                raise ValueError(f"V14 cell{cell}/column{column} zero-correction step changed z")
        else:
            delta = _load_array_ref(delta_ref, package=package, label=f"cell{cell}/column{column}/step{index}/delta")
            if delta.shape != rhs.shape:
                raise ValueError(f"V14 cell{cell}/column{column} step{index} delta shape differs")
            expected_after = np.asarray(z_before + delta, dtype=np.complex128)
            if not np.array_equal(z_after, expected_after):
                raise ValueError(f"V14 cell{cell}/column{column} step{index} update is not the returned delta")
            correction_count += 1
        current_state = np.asarray(z_after, dtype=np.complex128)
        getrs_count += int(delta_ref is not None)
        if (
            int(event.get("correction_getrs_count", -1)) != correction_count
            or int(event.get("getrs_count", -1)) != getrs_count
        ):
            raise ValueError(f"V14 cell{cell}/column{column} step GETRS accounting differs")
    final_event = events[-1]
    final_solved = _load_array_ref(final_event.get("solved"), package=package, label=f"cell{cell}/column{column}/final_event_z")
    if not np.array_equal(final_solved, current_state) or int(final_event.get("getrs_count", -1)) != getrs_count:
        raise ValueError(f"V14 cell{cell}/column{column} final callback differs from the step chain")
    final_z = _load_array_ref(record.get("final_z"), package=package, label=f"cell{cell}/column{column}/final_z")
    if not np.array_equal(final_z, current_state):
        raise ValueError(f"V14 cell{cell}/column{column} final z differs from saved callback chain")
    final_residual, final_metrics, final_row_scale = _wide_residual(matrix, rhs, final_z)
    residual_rows.append({"state": "final", **final_metrics})
    correction = _load_array_ref(record.get("returned_correction"), package=package, label=f"cell{cell}/column{column}/returned_correction")
    final_callback_correction = _load_array_ref(final_event.get("correction"), package=package, label=f"cell{cell}/column{column}/final_event_correction")
    exact_returned = np.asarray(-(local["J"] @ final_z), dtype=np.complex128)
    if not np.array_equal(correction, final_callback_correction) or not np.array_equal(correction, exact_returned):
        raise ValueError(f"V14 cell{cell}/column{column} returned correction is not the exact complex128 -J@z output")
    wide_correction = -np.asarray(local["J"], dtype=np.clongdouble) @ np.asarray(final_z, dtype=np.clongdouble)
    correction_scale = np.abs(np.asarray(local["J"], dtype=np.clongdouble)) @ np.abs(np.asarray(final_z, dtype=np.clongdouble)) + np.abs(wide_correction)
    correction_mismatch = _close_to_wide(
        correction, wide_correction, correction_scale,
        label=f"cell{cell}/column{column} actual returned -Jz",
    )
    projected = _load_array_ref(record.get("projected_active"), package=package, label=f"cell{cell}/column{column}/projected_active")
    wide_projection = np.asarray(local["trace_expansion"].toarray(), dtype=np.clongdouble).conj().T @ np.asarray(correction, dtype=np.clongdouble)
    projection_scale = np.abs(np.asarray(local["trace_expansion"].toarray(), dtype=np.clongdouble)).T @ np.abs(np.asarray(correction, dtype=np.clongdouble)) + np.abs(wide_projection)
    projection_mismatch = _close_to_wide(
        projected, wide_projection, projection_scale,
        label=f"cell{cell}/column{column} active projection",
    )
    timing = record.get("timing")
    if not isinstance(timing, Mapping) or int(timing.get("getrs_count", -1)) != getrs_count:
        raise ValueError(f"V14 cell{cell}/column{column} timing GETRS count differs from saved calls")
    residual_resolution = max(
        initial_metrics["wide_evaluation_resolution_l2"],
        final_metrics["wide_evaluation_resolution_l2"],
    )
    residual_delta = initial_metrics["absolute_l2"] - final_metrics["absolute_l2"]
    if final_metrics["absolute_l2"] > initial_metrics["absolute_l2"] + residual_resolution:
        residual_verdict = "worsened"
    elif residual_delta > residual_resolution:
        residual_verdict = "credible_improvement"
    else:
        residual_verdict = "inconclusive"
    return {
        "cell_index": cell,
        "column": column,
        "getrs_count": getrs_count,
        "correction_getrs_count": correction_count,
        "residuals_450_rows": residual_rows,
        "residual_gate": residual_verdict,
        "residual_improvement_l2": float(residual_delta),
        "actual_returned_correction_max_abs_difference": correction_mismatch,
        "projected_active_max_abs_difference": projection_mismatch,
        "final_correction_sha256": record["returned_correction"]["sha256"],
    }


def check_v14_saved_candidate(
    *, source: Mapping[str, Any], candidate_report_path: str | Path,
    candidate_report_sha256: str, output_path: str | Path,
) -> dict[str, Any]:
    candidate_path = Path(candidate_report_path).resolve(strict=True)
    package = candidate_path.parent.resolve(strict=True)
    if not package.is_relative_to(source["results_root"]):
        raise ValueError("V14 candidate package escaped the Task41 results root")
    if candidate_path.stat().st_size > 16 * 1024**2 or sha256_file(candidate_path) != candidate_report_sha256:
        raise ValueError("V14 candidate report path/size/hash differs")
    report = json.loads(candidate_path.read_text(encoding="utf-8"))
    expected_columns = list(V14_COLUMNS)
    expected_states = ["j0" if value == 0 else "j3" for value in V14_COLUMNS]
    if (
        report.get("schema") != V14_CANDIDATE_REPORT_SCHEMA
        or report.get("status") != "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK"
        or report.get("official_result") is not False
        or report.get("scientific_qualified") is not False
        or report.get("consumer_contract_sha256") != source["consumer_contract_sha256"]
        or report.get("consumer_window_sha256") != source["consumer_window_sha256"]
        or report.get("producer_report_sha256") != source["producer_report_sha256"]
        or report.get("accepted_checker_sha256") != source["accepted_checker_sha256"]
        or report.get("accepted_receipt_sha256") != source["accepted_receipt_sha256"]
        or report.get("donor_manifest_sha256") != source["donor_manifest_sha256"]
        or report.get("producer_window_sha256") != V14_SOURCE_WINDOW_SHA256
        or report.get("consumer_contract_path") != str(source["consumer_contract_path"])
    ):
        raise ValueError("V14 candidate/report source identities or negative classification differ")
    stage = report.get("scope")
    if (
        not isinstance(stage, Mapping)
        or stage.get("stage") != "initial_screen"
        or stage.get("cells") != list(V14_CELLS)
        or stage.get("columns") != expected_columns
        or stage.get("states") != expected_states
        or stage.get("max_correction_steps") != 2
        or stage.get("max_initial_screen_getrs_count") != 12
        or stage.get("conditional_star_coverage_registered") is not True
        or stage.get("full_owner") is not False
    ):
        raise ValueError("V14 candidate does not describe the bounded initial screen")
    rows = report.get("candidate_rhs")
    if not isinstance(rows, list) or len(rows) != len(V14_CELLS) * len(V14_COLUMNS):
        raise ValueError("V14 candidate RHS inventory does not contain exactly four items")
    keys = [(int(row.get("cell_index", -1)), int(row.get("column", -1))) for row in rows]
    expected_keys = [(cell, column) for cell in V14_CELLS for column in V14_COLUMNS]
    if sorted(keys) != sorted(expected_keys) or len(set(keys)) != len(keys):
        raise ValueError("V14 candidate RHS inventory has missing or duplicate cell/column pairs")
    rhs_checks = [
        _check_rhs(source=source, package=package, record=row)
        for row in rows
    ]
    if sum(int(item["getrs_count"]) for item in rhs_checks) != int(report.get("getrs_count", -1)):
        raise ValueError("V14 candidate total GETRS differs from independently counted calls")
    if int(report.get("getrs_count", -1)) > 12:
        raise ValueError("V14 initial screen exceeded twelve GETRS calls")
    rhs_by_key = {(int(row["cell_index"]), int(row["column"])): row for row in rows}
    production_rows = report.get("production_order_rows")
    if not isinstance(production_rows, list) or len(production_rows) != len(V14_COLUMNS):
        raise ValueError("V14 production-order y/g/d rows are missing")
    d_checks: list[dict[str, Any]] = []
    rejected: list[str] = []
    inconclusive: list[str] = []
    for column in V14_COLUMNS:
        row = next((item for item in production_rows if int(item.get("column", -1)) == column), None)
        if not isinstance(row, Mapping):
            raise ValueError(f"V14 production-order column {column} is missing")
        b_t = source["b_t_by_column"][column]
        beta_t = source["b_alpha_by_column"][column]
        y = 0.0 + 0.0j
        base_g = complex(b_t)
        candidate_g = complex(b_t)
        base_terms: list[complex] = []
        candidate_terms: list[complex] = []
        for cell in V14_CELLS:
            local = source["cells"][cell]
            term = local["column_terms"][column]
            s_active = np.asarray(
                local["trace_expansion"].conj().T @ term["s_action"], dtype=np.complex128
            ).reshape(-1)
            old_active = np.asarray(
                local["trace_expansion"].conj().T @ term["old_correction"], dtype=np.complex128
            ).reshape(-1)
            y += complex(s_active[local["target_active_position"]])
            new_active = _load_array_ref(
                rhs_by_key[(cell, column)].get("projected_active"), package=package,
                label=f"cell{cell}/column{column}/production_projection",
            )
            old_piece = complex(old_active[local["target_active_position"]])
            new_piece = complex(new_active[local["target_active_position"]])
            base_terms.append(old_piece)
            candidate_terms.append(new_piece)
            base_g += old_piece
            candidate_g += new_piece
        y += beta_t
        baseline_ref = source["baseline_g_by_column"][column]
        if y != source["y_by_column"][column]:
            raise ValueError(f"V14 column {column} checker array-derived y differs from loader cross-check")
        if base_g != baseline_ref:
            raise ValueError(f"V14 column {column} array-derived g differs from the frozen production order")
        expected_pairs = {
            "saved_y": [y.real, y.imag],
            "baseline_g_replayed_cell_order": [base_g.real, base_g.imag],
            "candidate_g_actual_returned_correction_cell_order": [candidate_g.real, candidate_g.imag],
            "baseline_d": [(y - base_g).real, (y - base_g).imag],
            "candidate_d": [(y - candidate_g).real, (y - candidate_g).imag],
            "baseline_cell_terms": [[value.real, value.imag] for value in base_terms],
            "candidate_cell_terms": [[value.real, value.imag] for value in candidate_terms],
        }
        if (
            row.get("base_b_t_source") != source["b_t_ref_by_column"][column]
            or row.get("b_alpha_sources") != source["b_alpha_refs_by_column"][column]
            or row.get("b_alpha_row_used_once") != [beta_t.real, beta_t.imag]
            or row.get("y_cell_s_action_sources") != [source["cells"][cell]["column_terms"][column]["s_action_ref"] for cell in V14_CELLS]
        ):
            raise ValueError(f"V14 column {column} y/g array provenance differs")
        for field, expected in expected_pairs.items():
            actual = np.asarray(row.get(field), dtype=np.float64)
            wanted = np.asarray(expected, dtype=np.float64)
            if actual.shape != wanted.shape or not np.array_equal(actual, wanted):
                raise ValueError(f"V14 column {column} production-order {field} differs")
        y_wide = np.clongdouble(y)
        b_t_wide = np.clongdouble(b_t)
        baseline_g_wide = b_t_wide
        candidate_g_wide = b_t_wide
        for old_piece, new_piece in zip(base_terms, candidate_terms, strict=True):
            baseline_g_wide = baseline_g_wide + np.clongdouble(old_piece)
            candidate_g_wide = candidate_g_wide + np.clongdouble(new_piece)
        baseline_d_wide = y_wide - baseline_g_wide
        candidate_d_wide = y_wide - candidate_g_wide
        baseline_d_production = y - base_g
        candidate_d_production = y - candidate_g
        d_scale = abs(y_wide) + abs(b_t_wide) + sum(
            abs(np.clongdouble(value)) for value in base_terms + candidate_terms
        )
        d_resolution = float(
            np.longdouble(64 * len(V14_CELLS))
            * np.finfo(np.longdouble).eps
            * max(d_scale, np.finfo(np.longdouble).tiny)
        )
        d_delta_production = float(abs(baseline_d_production) - abs(candidate_d_production))
        d_delta_wide_diagnostic = float(abs(baseline_d_wide) - abs(candidate_d_wide))
        if d_delta_production > d_resolution:
            verdict = "improved"
        elif d_delta_production < -d_resolution:
            verdict = "worsened"
        else:
            verdict = "inconclusive"
        if verdict == "worsened":
            rejected.append(f"column{column}_d_worsened")
        elif verdict == "inconclusive":
            inconclusive.append(f"column{column}_d_change_within_wide_resolution")
        d_checks.append({
            "column": column,
            "baseline_d_abs_production_complex128": float(abs(baseline_d_production)),
            "candidate_d_abs_production_complex128": float(abs(candidate_d_production)),
            "production_order_improvement": d_delta_production,
            "baseline_d_abs_wide_diagnostic": float(abs(baseline_d_wide)),
            "candidate_d_abs_wide_diagnostic": float(abs(candidate_d_wide)),
            "wide_d_improvement_diagnostic_only": d_delta_wide_diagnostic,
            "wide_evaluation_resolution": d_resolution,
            "verdict": verdict,
        })
    for item in rhs_checks:
        if item["residual_gate"] == "worsened":
            rejected.append(f"cell{item['cell_index']}_column{item['column']}_true_residual_worsened")
        elif item["residual_gate"] == "inconclusive":
            inconclusive.append(f"cell{item['cell_index']}_column{item['column']}_true_residual_change_within_wide_resolution")
    package_bytes = sum(path.stat().st_size for path in package.rglob("*") if path.is_file())
    if package_bytes > 16 * 1024**2:
        raise ValueError("V14 initial screen evidence package exceeds 16 MiB")
    if rejected:
        status = "LOCAL_CANDIDATE_REJECTED"
        passed: bool | None = False
    elif inconclusive:
        status = "INCONCLUSIVE"
        passed = None
    else:
        status = "LOCAL_CANDIDATE_PASS"
        passed = True
    payload = {
        "schema": V14_CANDIDATE_CHECK_SCHEMA,
        "status": status,
        "classification": status,
        "check_completed": True,
        "candidate_passed": passed,
        "scientific_qualified": False,
        "official_result": False,
        "candidate_report_path": str(candidate_path),
        "candidate_report_sha256": candidate_report_sha256,
        "consumer_contract_sha256": source["consumer_contract_sha256"],
        "consumer_window_sha256": source["consumer_window_sha256"],
        "producer_report_sha256": source["producer_report_sha256"],
        "scope": {"stage": "initial_screen", "cells": list(V14_CELLS), "columns": expected_columns, "states": expected_states},
        "getrs_count_rechecked": int(report["getrs_count"]),
        "candidate_package_bytes": package_bytes,
        "rhs_checks": rhs_checks,
        "production_order_d_checks": d_checks,
        "rejection_reasons": rejected,
        "inconclusive_reasons": inconclusive,
        "conditional_star_coverage_unlocked": passed is True,
        "full_owner_unlocked": False,
    }
    out = Path(output_path).resolve()
    if not out.is_relative_to(source["results_root"]):
        raise ValueError("V14 checker output must stay under the Task41 results root")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise FileExistsError(f"V14 checker output already exists: {out}")
    temporary = out.with_name(f".{out.name}.tmp")
    with temporary.open("xb") as stream:
        stream.write((json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, out)
    payload["path"] = str(out)
    payload["sha256"] = sha256_file(out)
    return payload


def _decimal_residual_metrics(
    matrix: np.ndarray, rhs: np.ndarray, state: np.ndarray, *, precision: int
) -> dict[str, Any]:
    """Evaluate all complex residual rows from exact Decimal conversions of binary64 inputs."""
    n = V14_EXPECTED_INTERNAL_ROWS
    if (
        matrix.shape != (n, n)
        or rhs.shape != (n,)
        or state.shape != (n,)
        or matrix.dtype != np.dtype(np.complex128)
        or rhs.dtype != np.dtype(np.complex128)
        or state.dtype != np.dtype(np.complex128)
    ):
        raise ValueError("V14 Decimal residual inputs are not the frozen complex128 450-row layout")

    def dec(value: float) -> Decimal:
        return Decimal.from_float(float(value))

    with localcontext() as context:
        context.prec = precision
        context.rounding = ROUND_HALF_EVEN
        zero = Decimal(0)
        residual_rows: list[dict[str, str | int]] = []
        sum_residual_sq = zero
        sum_rhs_sq = zero
        sum_input_scale_sq = zero
        max_row_sq = zero
        max_row_index = -1
        for row_index in range(n):
            b_value = rhs[row_index]
            b_real, b_imag = dec(b_value.real), dec(b_value.imag)
            dot_real = dot_imag = zero
            scale_real, scale_imag = abs(b_real), abs(b_imag)
            for column in range(n):
                a_value, z_value = matrix[row_index, column], state[column]
                a_real, a_imag = dec(a_value.real), dec(a_value.imag)
                z_real, z_imag = dec(z_value.real), dec(z_value.imag)
                rr, ri = a_real * z_real, a_imag * z_imag
                ir, ii = a_real * z_imag, a_imag * z_real
                dot_real = dot_real + (rr - ri)
                dot_imag = dot_imag + (ir + ii)
                scale_real = scale_real + abs(rr) + abs(ri)
                scale_imag = scale_imag + abs(ir) + abs(ii)
            residual_real, residual_imag = b_real - dot_real, b_imag - dot_imag
            row_sq = residual_real * residual_real + residual_imag * residual_imag
            sum_residual_sq += row_sq
            sum_rhs_sq += b_real * b_real + b_imag * b_imag
            sum_input_scale_sq += scale_real * scale_real + scale_imag * scale_imag
            if row_sq > max_row_sq:
                max_row_sq, max_row_index = row_sq, row_index
            residual_rows.append({
                "row": row_index,
                "real": str(residual_real),
                "imag": str(residual_imag),
            })
        absolute_l2, absolute_inf = sum_residual_sq.sqrt(), max_row_sq.sqrt()
        rhs_l2, input_scale_l2 = sum_rhs_sq.sqrt(), sum_input_scale_sq.sqrt()
        relative_rhs_l2 = absolute_l2 / max(
            rhs_l2, Decimal.from_float(float(np.finfo(float).tiny))
        )
        # Inflated standard round-to-nearest arithmetic-model bound. Decimal.from_float
        # imports every complex128 component exactly; this excludes input/solver errors.
        operations = 32 * n + 32
        unit_roundoff = Decimal(5).scaleb(-precision)
        gamma = operations * unit_roundoff / (Decimal(1) - operations * unit_roundoff)
        arithmetic_bound = Decimal(2) * gamma * input_scale_l2
        return {
            "precision": precision,
            "row_count": n,
            "absolute_l2": str(absolute_l2),
            "absolute_inf": str(absolute_inf),
            "absolute_inf_row": max_row_index,
            "relative_rhs_l2": str(relative_rhs_l2),
            "componentwise_input_scale_l2": str(input_scale_l2),
            "unit_roundoff_decimal": str(unit_roundoff),
            "rounding_mode": "ROUND_HALF_EVEN",
            "conservative_decimal_arithmetic_bound": str(arithmetic_bound),
            "row_residuals": residual_rows,
        }


def check_v14_saved_candidate_decimal_residuals(
    *,
    repo_root: str | Path,
    source: Mapping[str, Any],
    candidate_report_path: str | Path,
    candidate_report_sha256: str,
    prior_independent_check_path: str | Path,
    prior_independent_check_sha256: str,
    review_contract_path: str | Path,
    review_contract_sha256: str,
    output_path: str | Path,
) -> dict[str, Any]:
    """Add a Decimal residual diagnostic without changing candidate qualification."""
    root = Path(repo_root).resolve(strict=True)
    results_root = Path(source["results_root"]).resolve(strict=True)
    output = Path(output_path).resolve()
    if not output.is_relative_to(results_root) or output.exists():
        raise ValueError("V14 Decimal diagnostic output path is invalid or already exists")
    wide_replay_path = output.with_name("task41_p0_v14_saved_rhs_decimal_wide_recheck.json")
    if wide_replay_path.exists():
        raise FileExistsError(f"V14 Decimal wide recheck already exists: {wide_replay_path}")
    candidate_path = Path(candidate_report_path).resolve(strict=True)
    prior_path = Path(prior_independent_check_path).resolve(strict=True)
    if (
        not candidate_path.is_relative_to(results_root)
        or not prior_path.is_relative_to(results_root)
        or candidate_path.stat().st_size > 16 * 1024**2
        or prior_path.stat().st_size > 16 * 1024**2
        or sha256_file(candidate_path) != candidate_report_sha256
        or sha256_file(prior_path) != prior_independent_check_sha256
    ):
        raise ValueError("V14 Decimal diagnostic input path, size, or SHA-256 differs")

    review_path = Path(review_contract_path).resolve(strict=True)
    review_contract, review_digest = require_task41_p0_contract(
        review_path,
        expected_sha256=review_contract_sha256,
        current_root=root,
        check_current_source=True,
        require_clean_source=True,
        case_id="B0",
    )
    old_contract = source["consumer_contract"]
    old_window = load_task41_p0_fixed_window(
        old_contract, current_root=root, require_current_boot=False
    )
    review_window = load_task41_p0_fixed_window(
        review_contract, current_root=root, require_current_boot=False
    )
    if (
        review_contract.get("execution_scope") != TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE
        or review_contract.get("source", {}).get("sha")
        == old_contract.get("source", {}).get("sha")
        or review_window.sha256 != old_window.sha256
        or Path(review_window.path).resolve() != Path(old_window.path).resolve()
        or review_window.sha256 != source["consumer_window_sha256"]
    ):
        raise ValueError("V14 Decimal review contract is not a new-source binding to the same fixed window")

    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    if (
        candidate.get("schema") != V14_CANDIDATE_REPORT_SCHEMA
        or candidate.get("status") != "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK"
        or candidate.get("official_result") is not False
        or candidate.get("scientific_qualified") is not False
        or candidate.get("consumer_contract_path") != str(source["consumer_contract_path"])
        or candidate.get("consumer_contract_sha256") != source["consumer_contract_sha256"]
        or candidate.get("consumer_window_sha256") != source["consumer_window_sha256"]
        or prior.get("schema") != V14_CANDIDATE_CHECK_SCHEMA
        or prior.get("status") != "INCONCLUSIVE"
        or prior.get("check_completed") is not True
        or prior.get("candidate_passed") is not None
        or prior.get("official_result") is not False
        or prior.get("scientific_qualified") is not False
        or prior.get("candidate_report_path") != str(candidate_path)
        or prior.get("candidate_report_sha256") != candidate_report_sha256
        or prior.get("consumer_contract_sha256") != source["consumer_contract_sha256"]
        or prior.get("consumer_window_sha256") != source["consumer_window_sha256"]
    ):
        raise ValueError("V14 Decimal diagnostic is not bound to the original INCONCLUSIVE candidate/check")
    scope, rows = candidate.get("scope"), candidate.get("candidate_rhs")
    expected_keys = [(cell, column) for cell in V14_CELLS for column in V14_COLUMNS]
    if (
        not isinstance(scope, Mapping)
        or scope.get("stage") != "initial_screen"
        or scope.get("cells") != list(V14_CELLS)
        or scope.get("columns") != list(V14_COLUMNS)
        or scope.get("full_owner") is not False
        or not isinstance(rows, list)
        or len(rows) != len(expected_keys)
    ):
        raise ValueError("V14 Decimal diagnostic candidate scope or four-RHS inventory differs")
    keys = [(int(row.get("cell_index", -1)), int(row.get("column", -1))) for row in rows]
    if sorted(keys) != sorted(expected_keys) or len(set(keys)) != len(keys):
        raise ValueError("V14 Decimal diagnostic candidate has missing or duplicate RHS entries")

    package = candidate_path.parent.resolve(strict=True)
    # Reuse the original checker unchanged for returned corrections and production-order y/g/d.
    # Its saved-array replay performs no solve/GETRS and its output is kept beside this supplement.
    wide_replay = check_v14_saved_candidate(
        source=source,
        candidate_report_path=candidate_path,
        candidate_report_sha256=candidate_report_sha256,
        output_path=wide_replay_path,
    )
    if (
        wide_replay.get("getrs_count_rechecked") != candidate.get("getrs_count")
        or wide_replay.get("full_owner_unlocked") is not False
    ):
        raise ValueError("V14 original saved-array checker replay did not preserve its bounded scope")

    diagnostics: list[dict[str, Any]] = []
    rejected: list[str] = []
    inconclusive: list[str] = []
    for item in wide_replay["production_order_d_checks"]:
        column = int(item["column"])
        if item["verdict"] == "worsened":
            rejected.append(f"column{column}_d_worsened")
        elif item["verdict"] == "inconclusive":
            inconclusive.append(f"column{column}_d_change_within_wide_resolution")
    for row in rows:
        cell, column = int(row["cell_index"]), int(row["column"])
        local, term = source["cells"][cell], source["cells"][cell]["column_terms"][column]
        events = _load_event_log(
            row.get("initial_and_step_log"), package=package,
            label=f"cell{cell}/column{column}",
        )
        states = (
            ("initial", _load_array_ref(
                events[0].get("solved"), package=package,
                label=f"cell{cell}/column{column}/initial_z",
            )),
            ("final", _load_array_ref(
                row.get("final_z"), package=package,
                label=f"cell{cell}/column{column}/final_z",
            )),
        )
        state_results: list[dict[str, Any]] = []
        for state_name, state in states:
            result_50 = _decimal_residual_metrics(local["K"], term["b_i"], state, precision=50)
            result_80 = _decimal_residual_metrics(local["K"], term["b_i"], state, precision=80)
            with localcontext() as context:
                context.prec = 100
                l2_50, l2_80 = Decimal(result_50["absolute_l2"]), Decimal(result_80["absolute_l2"])
                bound_50 = Decimal(result_50["conservative_decimal_arithmetic_bound"])
                bound_80 = Decimal(result_80["conservative_decimal_arithmetic_bound"])
                empirical_delta, paired_bound = abs(l2_50 - l2_80), bound_50 + bound_80
                interval_50 = [max(Decimal(0), l2_50 - bound_50), l2_50 + bound_50]
                interval_80 = [max(Decimal(0), l2_80 - bound_80), l2_80 + bound_80]
            state_results.append({
                "state": state_name,
                "precision_50": result_50,
                "precision_80": result_80,
                "residual_l2_interval_precision_50": [str(value) for value in interval_50],
                "residual_l2_interval_precision_80": [str(value) for value in interval_80],
                "empirical_precision_delta_l2": str(empirical_delta),
                "combined_conservative_decimal_arithmetic_bound": str(paired_bound),
                "empirical_delta_within_combined_bound": empirical_delta <= paired_bound,
                "precision_comparison_is_diagnostic_not_a_theorem": True,
            })
        state_by_name = {item["state"]: item for item in state_results}
        initial_state = state_by_name["initial"]
        final_state = state_by_name["final"]
        initial_interval = [
            min(
                Decimal(initial_state["residual_l2_interval_precision_50"][0]),
                Decimal(initial_state["residual_l2_interval_precision_80"][0]),
            ),
            max(
                Decimal(initial_state["residual_l2_interval_precision_50"][1]),
                Decimal(initial_state["residual_l2_interval_precision_80"][1]),
            ),
        ]
        final_interval = [
            min(
                Decimal(final_state["residual_l2_interval_precision_50"][0]),
                Decimal(final_state["residual_l2_interval_precision_80"][0]),
            ),
            max(
                Decimal(final_state["residual_l2_interval_precision_50"][1]),
                Decimal(final_state["residual_l2_interval_precision_80"][1]),
            ),
        ]
        if final_interval[1] < initial_interval[0]:
            residual_verdict = "credible_improvement"
        elif final_interval[0] > initial_interval[1]:
            residual_verdict = "worsened"
        else:
            residual_verdict = "inconclusive"
        precision_bounds_ok = all(
            item["empirical_delta_within_combined_bound"] for item in state_results
        )
        diagnostics.append({
            "cell_index": cell,
            "column": column,
            "rhs_identity_sha256": row.get("b_i", {}).get("sha256"),
            "initial_final_residuals": state_results,
            "combined_precision_l2_intervals": {
                "combination": "union_envelope_of_precision_50_and_precision_80",
                "initial": [str(value) for value in initial_interval],
                "final": [str(value) for value in final_interval],
            },
            "decimal_residual_verdict": residual_verdict,
            "empirical_precision_deltas_within_bounds": precision_bounds_ok,
        })
        key = f"cell{cell}_column{column}"
        if residual_verdict == "worsened":
            rejected.append(f"{key}_true_residual_worsened")
        elif residual_verdict == "inconclusive" or not precision_bounds_ok:
            inconclusive.append(f"{key}_true_residual_not_credibly_improved")
    if rejected:
        status = "LOCAL_CANDIDATE_REJECTED"
        passed: bool | None = False
    elif inconclusive:
        status = "INCONCLUSIVE"
        passed = None
    else:
        status = "LOCAL_CANDIDATE_PASS"
        passed = True
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "task41.p0.v14.saved_rhs_decimal_residual_recheck.v1",
        "status": status,
        "classification": "DECIMAL_SUPPLEMENTAL_INDEPENDENT_CHECK",
        "check_completed": True,
        "official_result": False,
        "scientific_qualified": False,
        "candidate_passed": passed,
        "conditional_star_coverage_unlocked": passed is True,
        "full_owner_unlocked": False,
        "numerical_work_started": False,
        "getrs_invoked": 0,
        "getrs_added": 0,
        "wide_replay_path": wide_replay["path"],
        "wide_replay_sha256": wide_replay["sha256"],
        "production_order_d_checks": wide_replay["production_order_d_checks"],
        "rejection_reasons": rejected,
        "inconclusive_reasons": inconclusive,
        "prior_check_status": prior["status"],
        "prior_independent_check_path": str(prior_path),
        "prior_independent_check_sha256": prior_independent_check_sha256,
        "candidate_report_path": str(candidate_path),
        "candidate_report_sha256": candidate_report_sha256,
        "consumer_contract_path": str(source["consumer_contract_path"]),
        "consumer_contract_sha256": source["consumer_contract_sha256"],
        "review_contract_path": str(review_path),
        "review_contract_sha256": review_digest,
        "fixed_window_path": str(review_window.path),
        "fixed_window_sha256": review_window.sha256,
        "source_sha": review_contract["source"]["sha"],
        "arithmetic_method": (
            "Decimal.from_float imports each complex128 component exactly; direct complex "
            "matrix-vector residual over all 450 rows at precision 50 and 80."
        ),
        "conservative_bound_model": (
            "2*gamma_m*L2(componentwise absolute input scales), u=5*10^-precision, "
            "m=32*450+32, explicit ROUND_HALF_EVEN; a conservative standard arithmetic "
            "model bound, not a theorem about source, discretization, or candidate-solve error."
        ),
        "rhs_count": len(diagnostics),
        "state_count": sum(len(item["initial_final_residuals"]) for item in diagnostics),
        "rows_per_state": V14_EXPECTED_INTERNAL_ROWS,
        "diagnostics": diagnostics,
    }
    temporary = output.with_name(f".{output.name}.tmp")
    with temporary.open("xb") as stream:
        stream.write((json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, output)
    payload["path"] = str(output)
    payload["sha256"] = sha256_file(output)
    return payload


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--consumer-contract", required=True, type=Path)
    parser.add_argument("--consumer-contract-sha256", required=True)
    parser.add_argument("--producer-report", required=True, type=Path)
    parser.add_argument("--producer-report-sha256", required=True)
    parser.add_argument("--accepted-checker", required=True, type=Path)
    parser.add_argument("--accepted-checker-sha256", required=True)
    parser.add_argument("--accepted-receipt", required=True, type=Path)
    parser.add_argument("--accepted-receipt-sha256", required=True)
    parser.add_argument("--donor-summary", required=True, type=Path)
    parser.add_argument("--donor-summary-sha256", required=True)
    parser.add_argument("--donor-contract", required=True, type=Path)
    parser.add_argument("--donor-contract-sha256", required=True)
    parser.add_argument("--candidate-report", required=True, type=Path)
    parser.add_argument("--candidate-report-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--decimal-residual-recheck-only", action="store_true")
    parser.add_argument("--review-contract", type=Path)
    parser.add_argument("--review-contract-sha256")
    parser.add_argument("--prior-independent-check", type=Path)
    parser.add_argument("--prior-independent-check-sha256")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    source = load_v14_saved_candidate_inputs(
        repo_root=args.repo_root,
        consumer_contract_path=args.consumer_contract,
        consumer_contract_sha256=args.consumer_contract_sha256,
        producer_report_path=args.producer_report,
        producer_report_sha256=args.producer_report_sha256,
        accepted_checker_path=args.accepted_checker,
        accepted_checker_sha256=args.accepted_checker_sha256,
        accepted_receipt_path=args.accepted_receipt,
        accepted_receipt_sha256=args.accepted_receipt_sha256,
        donor_summary_path=args.donor_summary,
        donor_summary_sha256=args.donor_summary_sha256,
        donor_contract_path=args.donor_contract,
        donor_contract_sha256=args.donor_contract_sha256,
        check_current_source=not args.decimal_residual_recheck_only,
        require_clean_source=not args.decimal_residual_recheck_only,
    )
    if args.decimal_residual_recheck_only:
        if (
            args.review_contract is None
            or args.review_contract_sha256 is None
            or args.prior_independent_check is None
            or args.prior_independent_check_sha256 is None
        ):
            raise ValueError("Decimal residual mode requires review-contract and prior-check bindings")
        result = check_v14_saved_candidate_decimal_residuals(
            repo_root=args.repo_root,
            source=source,
            candidate_report_path=args.candidate_report,
            candidate_report_sha256=args.candidate_report_sha256,
            prior_independent_check_path=args.prior_independent_check,
            prior_independent_check_sha256=args.prior_independent_check_sha256,
            review_contract_path=args.review_contract,
            review_contract_sha256=args.review_contract_sha256,
            output_path=args.output,
        )
    else:
        result = check_v14_saved_candidate(
            source=source,
            candidate_report_path=args.candidate_report,
            candidate_report_sha256=args.candidate_report_sha256,
            output_path=args.output,
        )
    print(json.dumps({key: value for key, value in result.items() if key not in {"rhs_checks", "diagnostics"}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
