"""Independently check hash-bound V14 saved same-LU RHS candidate evidence."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from src.runners.task41_p0_contract import sha256_file
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
    )
    result = check_v14_saved_candidate(
        source=source,
        candidate_report_path=args.candidate_report,
        candidate_report_sha256=args.candidate_report_sha256,
        output_path=args.output,
    )
    print(json.dumps({key: value for key, value in result.items() if key != "rhs_checks"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
