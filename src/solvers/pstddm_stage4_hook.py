"""Typed sparse raw-port payload helpers for the p6 Stage-4 diagnostic path."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class PstddmRawPortColumn:
    """One mode's original full-row C/D and the already assembled reduced C/D/H."""

    index: int
    side: str
    m: int
    n: int
    polarization: str
    normalization: float
    raw_C_rows: np.ndarray
    raw_C_values: np.ndarray
    raw_D_rows: np.ndarray
    raw_D_values: np.ndarray
    reduced_C_rows: np.ndarray
    reduced_C_values: np.ndarray
    reduced_D_rows: np.ndarray
    reduced_D_values: np.ndarray
    raw_H: complex = 1.0 + 0.0j
    reduced_H: complex = 1.0 + 0.0j

    def __post_init__(self) -> None:
        if self.index < 0 or self.side not in {"top", "bottom"}:
            raise ValueError("invalid p6 raw-port mode identity")
        if not np.isfinite(self.normalization) or self.normalization <= 0.0:
            raise ValueError("raw-port mode normalization must be finite and positive")
        for rows_name, values_name in (
            ("raw_C_rows", "raw_C_values"),
            ("raw_D_rows", "raw_D_values"),
            ("reduced_C_rows", "reduced_C_values"),
            ("reduced_D_rows", "reduced_D_values"),
        ):
            rows = np.asarray(getattr(self, rows_name), dtype=np.int64).copy()
            values = np.asarray(getattr(self, values_name), dtype=np.complex128).copy()
            if rows.ndim != 1 or values.ndim != 1 or rows.shape != values.shape:
                raise ValueError("raw-port sparse row/value arrays must be parallel vectors")
            if np.any(rows < 0) or np.any(rows[1:] <= rows[:-1]):
                raise ValueError("raw-port sparse row arrays must be nonnegative and unique")
            if not np.isfinite(values).all():
                raise ValueError("raw-port sparse values must be finite")
            rows.setflags(write=False)
            values.setflags(write=False)
            object.__setattr__(self, rows_name, rows)
            object.__setattr__(self, values_name, values)
        if not np.isfinite(complex(self.raw_H)) or not np.isfinite(complex(self.reduced_H)):
            raise ValueError("raw-port H values must be finite")


def exact_sparse_entries(rows: Any, values: Any) -> tuple[np.ndarray, np.ndarray]:
    """Sort and exactly sum duplicate sparse rows without a magnitude cutoff."""

    row_array = np.asarray(rows, dtype=np.int64)
    value_array = np.asarray(values, dtype=np.complex128)
    if row_array.ndim != 1 or value_array.ndim != 1 or row_array.shape != value_array.shape:
        raise ValueError("sparse rows and values must be parallel vectors")
    if np.any(row_array < 0) or not np.isfinite(value_array).all():
        raise ValueError("sparse entries must have nonnegative rows and finite values")
    if row_array.size == 0:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.complex128)
    order = np.argsort(row_array, kind="stable")
    sorted_rows = row_array[order]
    sorted_values = value_array[order]
    unique_rows, starts = np.unique(sorted_rows, return_index=True)
    summed = np.add.reduceat(sorted_values, starts)
    keep = summed != 0.0
    return unique_rows[keep], summed[keep]


def combine_exact_components(
    components: tuple[tuple[Any, Any], tuple[Any, Any]],
    coefficients: tuple[complex, complex],
) -> tuple[np.ndarray, np.ndarray]:
    """Combine two raw surface vectors while preserving every nonzero entry."""

    rows: list[np.ndarray] = []
    values: list[np.ndarray] = []
    for (component_rows, component_values), coefficient in zip(
        components, coefficients, strict=True
    ):
        coefficient = complex(coefficient)
        component_rows = np.asarray(component_rows, dtype=np.int64)
        component_values = np.asarray(component_values, dtype=np.complex128)
        if component_rows.shape != component_values.shape:
            raise ValueError("component rows and values must be parallel vectors")
        if component_rows.size and coefficient != 0.0:
            rows.append(component_rows)
            values.append(coefficient * component_values)
    if not rows:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.complex128)
    return exact_sparse_entries(np.concatenate(rows), np.concatenate(values))


def official_rta_allowed(*, diagnostic_only: bool, full_residual_passed: bool) -> bool:
    """Diagnostic PSTDDM runs never publish official R/T, even when residuals pass."""

    return not diagnostic_only and bool(full_residual_passed)


def diagnostic_port_metrics(
    metrics: dict[str, Any], *, full_residual: float, residual_limit: float
) -> dict[str, Any]:
    """Preserve computed port observables while explicitly withholding official status."""

    residual = float(full_residual)
    limit = float(residual_limit)
    if not np.isfinite(residual) or residual < 0.0:
        raise ValueError("diagnostic full residual must be finite and nonnegative")
    if not np.isfinite(limit) or limit <= 0.0:
        raise ValueError("diagnostic residual limit must be finite and positive")
    marked = dict(metrics)
    marked.update(
        {
            "diagnostic_only": True,
            "official_result": False,
            "official_rta_gate_pass": False,
            "full_augmented_true_residual_relative": residual,
            "full_augmented_true_residual_gate_limit": limit,
            "full_augmented_true_residual_gate_pass": residual <= limit,
        }
    )
    return marked


def should_run_diagnostic_postprocess(*, pstddm_diagnostic: bool, field_finite: bool) -> bool:
    """Keep finite PSTDDM iterate observables available when official status is false."""

    return bool(pstddm_diagnostic and field_finite)
