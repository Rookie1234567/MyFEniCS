"""Pure accounting for the two existing production sparse-entry cutoffs.

This module does not assemble a vector, create an action, or alter a cutoff.
The runtime caller supplies snapshots taken from the actual production workspace
and the outputs returned by the production cutoff helpers.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

RELATIVE_TOLERANCE = 1.0e-13
ABSOLUTE_FLOOR = 1.0e-30


def _entries(rows: Any, values: Any) -> tuple[np.ndarray, np.ndarray]:
    row_array = np.asarray(rows, dtype=np.int64).reshape(-1)
    value_array = np.asarray(values, dtype=np.complex128).reshape(-1)
    if row_array.shape != value_array.shape:
        raise ValueError("sparse row/value shapes differ")
    if not np.isfinite(value_array).all():
        raise FloatingPointError("sparse entry values are non-finite")
    if row_array.size > 1 and np.any(row_array[1:] <= row_array[:-1]):
        raise ValueError("sparse rows must be strictly increasing")
    return row_array, value_array


def cutoff_facts(values: Any, *, relative_tolerance: float = RELATIVE_TOLERANCE) -> dict[str, Any]:
    value_array = np.asarray(values, dtype=np.complex128).reshape(-1)
    if not np.isfinite(value_array).all():
        raise FloatingPointError("cutoff input contains non-finite values")
    maximum = float(np.max(np.abs(value_array), initial=0.0))
    relative_term = float(relative_tolerance) * maximum
    cutoff = max(ABSOLUTE_FLOOR, relative_term)
    return {
        "maximum_abs_value": maximum,
        "absolute_floor": ABSOLUTE_FLOOR,
        "relative_tolerance": float(relative_tolerance),
        "relative_term": relative_term,
        "actual_cutoff": cutoff,
        "dominant_cutoff_term": (
            "absolute_floor" if ABSOLUTE_FLOOR >= relative_term else "relative_term"
        ),
    }


def expected_component_filter(
    rows: Any, values: Any, *, relative_tolerance: float = RELATIVE_TOLERANCE
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    row_array, value_array = _entries(rows, values)
    facts = cutoff_facts(value_array, relative_tolerance=relative_tolerance)
    keep = np.abs(value_array) > facts["actual_cutoff"]
    kept_rows, kept_values = row_array[keep].copy(), value_array[keep].copy()
    removed = value_array[~keep]
    facts.update(
        {
            "input_entry_count": int(value_array.size),
            "input_nonzero_count": int(np.count_nonzero(value_array)),
            "kept_entry_count": int(kept_values.size),
            "removed_entry_count": int(removed.size),
            "removed_nonzero_count": int(np.count_nonzero(removed)),
            "removed_maximum_abs_value": float(np.max(np.abs(removed), initial=0.0)),
        }
    )
    return kept_rows, kept_values, facts


def merge_without_cutoff(
    component_entries: Sequence[tuple[Any, Any]], coefficients: Sequence[complex]
) -> tuple[np.ndarray, np.ndarray]:
    if len(component_entries) != len(coefficients):
        raise ValueError("component and coefficient counts differ")
    row_blocks: list[np.ndarray] = []
    value_blocks: list[np.ndarray] = []
    for (rows, values), coefficient in zip(component_entries, coefficients, strict=True):
        row_array, value_array = _entries(rows, values)
        coefficient_value = np.complex128(coefficient)
        if not np.isfinite(coefficient_value):
            raise FloatingPointError("component coefficient is non-finite")
        if row_array.size and abs(coefficient_value) > 0.0:
            row_blocks.append(row_array)
            value_blocks.append(coefficient_value * value_array)
    if not row_blocks:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.complex128)
    all_rows = np.concatenate(row_blocks)
    all_values = np.concatenate(value_blocks)
    order = np.argsort(all_rows, kind="mergesort")
    rows_sorted = all_rows[order]
    values_sorted = all_values[order]
    unique_rows, first = np.unique(rows_sorted, return_index=True)
    summed_values = np.add.reduceat(values_sorted, first)
    return unique_rows.astype(np.int64, copy=False), summed_values.astype(
        np.complex128, copy=False
    )


def expected_merged_filter(
    component_entries: Sequence[tuple[Any, Any]],
    coefficients: Sequence[complex],
    *,
    relative_tolerance: float = RELATIVE_TOLERANCE,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    rows, values = merge_without_cutoff(component_entries, coefficients)
    facts = cutoff_facts(values, relative_tolerance=relative_tolerance)
    keep = np.abs(values) > facts["actual_cutoff"]
    facts.update(
        {
            "unique_rows_before_cutoff": int(rows.size),
            "unique_rows_after_cutoff": int(np.count_nonzero(keep)),
            "removed_entry_count": int(np.count_nonzero(~keep)),
            "removed_nonzero_count": int(np.count_nonzero(values[~keep])),
            "removed_maximum_abs_value": float(
                np.max(np.abs(values[~keep]), initial=0.0)
            ),
        }
    )
    return rows, values, rows[keep].copy(), values[keep].copy(), facts


def arrays_match(
    expected_rows: Any, expected_values: Any, actual_rows: Any, actual_values: Any
) -> bool:
    e_rows, e_values = _entries(expected_rows, expected_values)
    a_rows, a_values = _entries(actual_rows, actual_values)
    return bool(np.array_equal(e_rows, a_rows) and np.array_equal(e_values, a_values))


def _dot(entries: tuple[np.ndarray, np.ndarray], field: np.ndarray, *, conjugate: bool) -> complex:
    rows, values = entries
    if rows.size and (int(rows[0]) < 0 or int(rows[-1]) >= field.size):
        raise ValueError("sparse global row lies outside the bound storage vector")
    used = np.conjugate(values) if conjugate else values
    return complex(np.dot(used, field[rows]))


def _product_scale(entries: tuple[np.ndarray, np.ndarray], field: np.ndarray) -> float:
    rows, values = entries
    return float(np.sum(np.abs(values) * np.abs(field[rows]), dtype=np.float64))


def _closure_facts(
    before: complex,
    after: complex,
    removed_dot: complex,
    product_scale: float,
    term_count: int,
) -> dict[str, Any]:
    residual = before - after - removed_dot
    eps = np.finfo(np.float64).eps
    bound = max(
        ABSOLUTE_FLOOR,
        256.0 * eps * max(1, int(term_count)) * max(
            product_scale, abs(before), abs(after), abs(removed_dot), np.finfo(float).tiny
        ),
    )
    return {
        "before_minus_after_complex": before - after,
        "deleted_dot_complex": removed_dot,
        "closure_residual_complex": residual,
        "closure_residual_abs": float(abs(residual)),
        "roundoff_bound_abs": float(bound),
        "closed_within_roundoff_bound": bool(abs(residual) <= bound),
        "classification_if_not_closed": "DIAGNOSTIC_IMPLEMENTATION_FAILURE_NOT_CUTOFF_EVIDENCE",
    }


def route_cutoff_accounting(
    raw_components: Sequence[tuple[Any, Any]],
    filtered_components: Sequence[tuple[Any, Any]],
    coefficients: Sequence[complex],
    final_rows: Any,
    final_values: Any,
    storage_values: Any,
    *,
    conjugate_combined_values: bool,
) -> dict[str, Any]:
    """Account raw -> component cutoff -> merged cutoff for one complex dot route."""
    if len(raw_components) != 2 or len(filtered_components) != 2 or len(coefficients) != 2:
        raise ValueError("this diagnostic route requires the two x/y components")
    storage = np.asarray(storage_values, dtype=np.complex128).reshape(-1)
    if not np.isfinite(storage).all():
        raise FloatingPointError("bound zero-slave storage is non-finite")
    raw = [ _entries(*entry) for entry in raw_components ]
    filtered = [ _entries(*entry) for entry in filtered_components ]
    raw_merged = merge_without_cutoff(raw, coefficients)
    component_merged = merge_without_cutoff(filtered, coefficients)
    final = _entries(final_rows, final_values)
    raw_dot = _dot(raw_merged, storage, conjugate=conjugate_combined_values)
    component_dot = _dot(component_merged, storage, conjugate=conjugate_combined_values)
    final_dot = _dot(final, storage, conjugate=conjugate_combined_values)

    component_removed_dots: list[complex] = []
    component_removed_scales: list[float] = []
    for (raw_rows, raw_values), (kept_rows, kept_values), coefficient in zip(
        raw, filtered, coefficients, strict=True
    ):
        keep_rows = set(map(int, kept_rows))
        mask = np.asarray([int(row) not in keep_rows for row in raw_rows], dtype=bool)
        removed = (raw_rows[mask], raw_values[mask] * np.complex128(coefficient))
        if conjugate_combined_values:
            removed = (removed[0], np.conjugate(removed[1]))
        component_removed_dots.append(_dot(removed, storage, conjugate=False))
        component_removed_scales.append(_product_scale(removed, storage))
    component_removed_dot = complex(sum(component_removed_dots, 0.0j))
    stage1_product_scale = (
        _product_scale(raw_merged, storage)
        + _product_scale(component_merged, storage)
        + sum(component_removed_scales)
    )
    stage1_closure = _closure_facts(
        raw_dot,
        component_dot,
        component_removed_dot,
        stage1_product_scale,
        sum(int(entry[0].size) for entry in raw)
        + int(raw_merged[0].size)
        + int(component_merged[0].size),
    )

    merged_rows, merged_values = component_merged
    final_row_set = set(map(int, final[0]))
    final_mask = np.asarray([int(row) in final_row_set for row in merged_rows], dtype=bool)
    removed_values = merged_values[~final_mask]
    if conjugate_combined_values:
        removed_values = np.conjugate(removed_values)
    merged_removed = (merged_rows[~final_mask], removed_values)
    merged_removed_dot = _dot(merged_removed, storage, conjugate=False)
    stage2_closure = _closure_facts(
        component_dot,
        final_dot,
        merged_removed_dot,
        _product_scale(component_merged, storage)
        + _product_scale(final, storage)
        + _product_scale(merged_removed, storage),
        int(merged_rows.size + final[0].size),
    )
    return {
        "dot_convention": (
            "conjugate(combined_projection_values) dot storage, production order"
            if conjugate_combined_values
            else "combined_coupling_values dot storage, non-conjugated; not physical power"
        ),
        "raw_untruncated_dot_complex": raw_dot,
        "after_component_cutoff_before_merge_dot_complex": component_dot,
        "after_production_merged_cutoff_dot_complex": final_dot,
        "component_cutoff_deleted_dot_by_component_complex": component_removed_dots,
        "component_cutoff_deleted_dot_total_complex": component_removed_dot,
        "component_cutoff_delta_closure": stage1_closure,
        "merged_cutoff_deleted_dot_complex": merged_removed_dot,
        "merged_cutoff_delta_closure": stage2_closure,
        "closure_passed": bool(
            stage1_closure["closed_within_roundoff_bound"]
            and stage2_closure["closed_within_roundoff_bound"]
        ),
        "cutoff_is_root_cause": "NOT_INFERRED_BY_ACCOUNTING_ALONE",
    }
