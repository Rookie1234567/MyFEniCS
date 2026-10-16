"""Scale-homogeneous cutoff accounting for a diagnostic-only Task40 candidate.

This module computes an independent oracle for the opt-in production helper
outputs.  It does not assemble a field, build a carrier/action, or qualify a
solver result.  There is deliberately no absolute cutoff floor.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

RELATIVE_TOLERANCE = 1.0e-13


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


def relative_cutoff_facts(
    values: Any, *, relative_tolerance: float = RELATIVE_TOLERANCE
) -> dict[str, Any]:
    value_array = np.asarray(values, dtype=np.complex128).reshape(-1)
    if not np.isfinite(value_array).all():
        raise FloatingPointError("relative-cutoff input contains non-finite values")
    tolerance = float(relative_tolerance)
    if not np.isfinite(tolerance) or not 0.0 < tolerance < 1.0:
        raise ValueError("scale-homogeneous cutoff requires 0 < relative_tolerance < 1")
    with np.errstate(over="ignore", invalid="ignore"):
        magnitudes = np.abs(value_array)
    if not np.isfinite(magnitudes).all():
        raise FloatingPointError("relative-cutoff magnitude overflowed")
    maximum = float(np.max(magnitudes, initial=0.0))
    if maximum == 0.0:
        normalized_maximum = 0.0
    else:
        normalized_maximum = float(np.max(magnitudes / maximum, initial=0.0))
    return {
        "maximum_abs_value": maximum,
        "relative_tolerance": tolerance,
        "normalized_keep_rule": "abs(value)/global_maximum > relative_tolerance",
        "absolute_floor": None,
        "absolute_floor_influences_rowset": False,
        "zero_vector_policy": "empty_rowset",
        "normalized_ratio_underflow_policy": (
            "ratio rounded to zero is below the positive 1e-13 threshold and is discarded"
        ),
        "maximum_normalized_magnitude": normalized_maximum,
        "nonzero_input_count": int(np.count_nonzero(value_array)),
    }


def expected_component_filter(
    rows: Any,
    values: Any,
    *,
    relative_tolerance: float = RELATIVE_TOLERANCE,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    row_array, value_array = _entries(rows, values)
    facts = relative_cutoff_facts(value_array, relative_tolerance=relative_tolerance)
    maximum = float(facts["maximum_abs_value"])
    if maximum == 0.0:
        keep = np.zeros(value_array.shape, dtype=bool)
    else:
        with np.errstate(under="ignore", divide="ignore", invalid="raise", over="raise"):
            ratios = np.abs(value_array) / maximum
        if not np.isfinite(ratios).all():
            raise FloatingPointError("normalized component magnitude is non-finite")
        keep = ratios > float(relative_tolerance)
    kept_rows, kept_values = row_array[keep].copy(), value_array[keep].copy()
    removed = value_array[~keep]
    facts.update(
        {
            "input_entry_count": int(value_array.size),
            "kept_entry_count": int(kept_values.size),
            "removed_entry_count": int(removed.size),
            "removed_nonzero_count": int(np.count_nonzero(removed)),
            "removed_maximum_abs_value": float(np.max(np.abs(removed), initial=0.0)),
        }
    )
    return kept_rows, kept_values, facts


def _merge_unfiltered(
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
            raise FloatingPointError("merge coefficient is non-finite")
        if coefficient_value == 0.0 or row_array.size == 0:
            continue
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            product = coefficient_value * value_array
        if not np.isfinite(product).all():
            raise FloatingPointError("unfiltered coefficient product overflowed")
        if np.any((value_array != 0.0) & (product == 0.0)):
            raise FloatingPointError("unfiltered coefficient product underflowed to zero")
        row_blocks.append(row_array)
        value_blocks.append(product)
    if not row_blocks:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.complex128)
    all_rows = np.concatenate(row_blocks)
    all_values = np.concatenate(value_blocks)
    order = np.argsort(all_rows, kind="mergesort")
    rows_sorted, values_sorted = all_rows[order], all_values[order]
    unique_rows, first = np.unique(rows_sorted, return_index=True)
    with np.errstate(over="ignore", invalid="ignore"):
        summed = np.add.reduceat(values_sorted, first)
    if not np.isfinite(summed).all():
        raise FloatingPointError("unfiltered merged values are non-finite")
    return unique_rows.astype(np.int64, copy=False), summed.astype(np.complex128, copy=False)


def expected_merged_filter(
    component_entries: Sequence[tuple[Any, Any]],
    coefficients: Sequence[complex],
    *,
    relative_tolerance: float = RELATIVE_TOLERANCE,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    rows, values = _merge_unfiltered(component_entries, coefficients)
    facts = relative_cutoff_facts(values, relative_tolerance=relative_tolerance)
    maximum = float(facts["maximum_abs_value"])
    if maximum == 0.0:
        keep = np.zeros(values.shape, dtype=bool)
    else:
        with np.errstate(under="ignore", divide="ignore", invalid="raise", over="raise"):
            ratios = np.abs(values) / maximum
        if not np.isfinite(ratios).all():
            raise FloatingPointError("normalized merged magnitude is non-finite")
        keep = ratios > float(relative_tolerance)
    facts.update(
        {
            "unique_rows_before_cutoff": int(rows.size),
            "unique_rows_after_cutoff": int(np.count_nonzero(keep)),
            "removed_entry_count": int(np.count_nonzero(~keep)),
            "removed_nonzero_count": int(np.count_nonzero(values[~keep])),
            "removed_maximum_abs_value": float(np.max(np.abs(values[~keep]), initial=0.0)),
        }
    )
    return rows, values, rows[keep].copy(), values[keep].copy(), facts


def arrays_match(expected_rows: Any, expected_values: Any, actual_rows: Any, actual_values: Any) -> bool:
    e_rows, e_values = _entries(expected_rows, expected_values)
    a_rows, a_values = _entries(actual_rows, actual_values)
    return bool(np.array_equal(e_rows, a_rows) and np.array_equal(e_values, a_values))


def _product_scale(entries: tuple[np.ndarray, np.ndarray], field: np.ndarray) -> tuple[str, int]:
    rows, values = entries
    if rows.size and (int(rows[0]) < 0 or int(rows[-1]) >= field.size):
        raise ValueError("sparse row lies outside the bound storage vector")
    wide_values = values.astype(np.clongdouble, copy=False)
    wide_field = field[rows].astype(np.clongdouble, copy=False)
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        products = np.abs(wide_values) * np.abs(wide_field)
        total = np.sum(products, dtype=np.longdouble)
    if not np.isfinite(total):
        raise FloatingPointError("long-double sum(abs(products)) is non-finite")
    return np.format_float_scientific(total, precision=24, unique=False), int(rows.size)


def _dot(
    entries: tuple[np.ndarray, np.ndarray], field: np.ndarray, *, conjugate: bool
) -> complex:
    rows, values = entries
    if rows.size and (int(rows[0]) < 0 or int(rows[-1]) >= field.size):
        raise ValueError("sparse row lies outside the bound storage vector")
    used = np.conjugate(values) if conjugate else values
    return complex(np.dot(used, field[rows]))


def _dot_facts(
    entries: tuple[np.ndarray, np.ndarray], field: np.ndarray, *, conjugate: bool
) -> dict[str, Any]:
    scale, terms = _product_scale(entries, field)
    return {
        "dot_complex": _dot(entries, field, conjugate=conjugate),
        "sum_abs_products_longdouble": scale,
        "term_count": terms,
        "conjugated_sparse_values": bool(conjugate),
    }


def _closure_facts(before: dict[str, Any], after: dict[str, Any], removed: dict[str, Any]) -> dict[str, Any]:
    residual = complex(before["dot_complex"] - after["dot_complex"] - removed["dot_complex"])
    scale = (
        np.longdouble(before["sum_abs_products_longdouble"])
        + np.longdouble(after["sum_abs_products_longdouble"])
        + np.longdouble(removed["sum_abs_products_longdouble"])
    )
    terms = int(before["term_count"] + after["term_count"] + removed["term_count"])
    eps = np.longdouble(np.finfo(np.float64).eps)
    operation_count = np.longdouble(max(1, 2 * terms + 3))
    eps_product = operation_count * eps
    gamma = eps_product / (1 - eps_product) if eps_product < 1 else np.longdouble(np.inf)
    error_estimate = gamma * scale
    residual_longdouble = np.longdouble(abs(residual))
    within_estimate = bool(
        np.isfinite(error_estimate) and residual_longdouble <= error_estimate
    )
    if scale > 0:
        relative_residual = float(residual_longdouble / scale)
    else:
        relative_residual = 0.0 if residual == 0j else None
    return {
        "closure_residual_complex": residual,
        "closure_residual_abs": float(abs(residual)),
        "sum_abs_products_longdouble": np.format_float_scientific(
            scale, precision=24, unique=False
        ),
        "term_count": terms,
        "closure_relative_to_sum_abs_products": relative_residual,
        "binary64_sumabs_reduction_error_estimate_longdouble": np.format_float_scientific(
            error_estimate, precision=24, unique=False
        ),
        "within_binary64_sumabs_reduction_estimate": within_estimate,
        "closure_bound_policy": "NO_ABSOLUTE_FLOOR; gamma_(2*terms+3)*sum_abs_products; arithmetic diagnostic only",
        "closure_is_qualification_gate": False,
        "classification": "ARITHMETIC_CLOSURE_DIAGNOSTIC_NOT_CARRIER_OR_FIELD_QUALIFICATION",
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
    """Report untruncated -> component -> merged candidate dots and closures."""

    if len(raw_components) != 2 or len(filtered_components) != 2 or len(coefficients) != 2:
        raise ValueError("candidate route requires two surface components")
    storage = np.asarray(storage_values, dtype=np.complex128).reshape(-1)
    if not np.isfinite(storage).all():
        raise FloatingPointError("candidate route storage contains non-finite values")
    raw = [_entries(*entry) for entry in raw_components]
    filtered = [_entries(*entry) for entry in filtered_components]
    raw_merged = _merge_unfiltered(raw, coefficients)
    component_merged = _merge_unfiltered(filtered, coefficients)
    final = _entries(final_rows, final_values)

    raw_dot = _dot_facts(raw_merged, storage, conjugate=conjugate_combined_values)
    component_dot = _dot_facts(component_merged, storage, conjugate=conjugate_combined_values)
    final_dot = _dot_facts(final, storage, conjugate=conjugate_combined_values)

    removed_component_dots: list[dict[str, Any]] = []
    for (raw_rows, raw_values), (kept_rows, _kept_values), coefficient in zip(
        raw, filtered, coefficients, strict=True
    ):
        keep = set(map(int, kept_rows))
        mask = np.asarray([int(row) not in keep for row in raw_rows], dtype=bool)
        removed_values = raw_values[mask] * np.complex128(coefficient)
        if conjugate_combined_values:
            removed_values = np.conjugate(removed_values)
        removed_component_dots.append(
            _dot_facts((raw_rows[mask], removed_values), storage, conjugate=False)
        )
    component_removed = complex(sum((item["dot_complex"] for item in removed_component_dots), 0.0j))
    component_removed_scale = np.sum(
        [np.longdouble(item["sum_abs_products_longdouble"]) for item in removed_component_dots],
        dtype=np.longdouble,
    )
    component_removed_terms = int(sum(item["term_count"] for item in removed_component_dots))
    component_removed_fact = {
        "dot_complex": component_removed,
        "sum_abs_products_longdouble": np.format_float_scientific(
            component_removed_scale, precision=24, unique=False
        ),
        "term_count": component_removed_terms,
    }
    stage1 = _closure_facts(raw_dot, component_dot, component_removed_fact)

    final_row_set = set(map(int, final[0]))
    removed_mask = np.asarray([int(row) not in final_row_set for row in component_merged[0]])
    removed_values = component_merged[1][removed_mask]
    if conjugate_combined_values:
        removed_values = np.conjugate(removed_values)
    merged_removed = _dot_facts(
        (component_merged[0][removed_mask], removed_values), storage, conjugate=False
    )
    stage2 = _closure_facts(component_dot, final_dot, merged_removed)

    return {
        "dot_convention": (
            "conjugate(combined projection values) dot same zero-slave storage"
            if conjugate_combined_values
            else "combined coupling values dot same zero-slave storage; non-conjugated, not physical power"
        ),
        "raw_untruncated_dot_complex": raw_dot["dot_complex"],
        "after_component_cutoff_before_merge_dot_complex": component_dot["dot_complex"],
        "after_production_merged_cutoff_dot_complex": final_dot["dot_complex"],
        "component_cutoff_deleted_dot_by_component_complex": [
            item["dot_complex"] for item in removed_component_dots
        ],
        "component_cutoff_deleted_dot_total_complex": component_removed,
        "component_cutoff_delta_closure": stage1,
        "merged_cutoff_deleted_dot_complex": merged_removed["dot_complex"],
        "merged_cutoff_delta_closure": stage2,
        "sum_abs_products_and_term_count": {
            "raw_untruncated": {
                "sum_abs_products_longdouble": raw_dot["sum_abs_products_longdouble"],
                "term_count": raw_dot["term_count"],
            },
            "after_component_cutoff": {
                "sum_abs_products_longdouble": component_dot["sum_abs_products_longdouble"],
                "term_count": component_dot["term_count"],
            },
            "after_merged_cutoff": {
                "sum_abs_products_longdouble": final_dot["sum_abs_products_longdouble"],
                "term_count": final_dot["term_count"],
            },
        },
        "closure_passed": bool(
            stage1["within_binary64_sumabs_reduction_estimate"]
            and stage2["within_binary64_sumabs_reduction_estimate"]
        ),
        "closure_is_qualification_gate": False,
        "cutoff_is_root_cause": "NOT_INFERRED_BY_ACCOUNTING_ALONE",
    }
