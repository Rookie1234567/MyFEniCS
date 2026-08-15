"""Small action-only measurement core for the fixed W13A composition probe."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import time
from typing import Any

import numpy as np


W13A_SCHEMA = "task037.extra.m6b.w13a.projected-range-composition.v1"
W13A_RESIDUAL_ORDER = ("w5_iter200", "w7_cumulative400")
W13A_CLOSURE_LIMIT = 1.0e-11


def _finite_scalar(value: Any, name: str) -> float:
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"W13A {name} is nonfinite")
    return result


def _pair(value: Any, name: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"W13A {name} is not a real-imag pair")
    return [_finite_scalar(value[0], f"{name}.real"), _finite_scalar(value[1], f"{name}.imag")]


def _measurement_record(measurement: Mapping[str, Any]) -> dict[str, Any]:
    if measurement.get("finite") is not True:
        raise ValueError("W13A projected measurement is not finite")
    actions = measurement.get("action_counts")
    if actions != {"local_apply": 1, "physical_outer_action": 5, "range_apply": 3}:
        raise ValueError("W13A projected measurement action counts are not fixed")
    result = {
        "finite": True,
        "rho_local_only": _finite_scalar(measurement["rho_local_only"], "rho_local_only"),
        "rho_range_only": _finite_scalar(measurement["rho_range_only"], "rho_range_only"),
        "rho_projected": _finite_scalar(measurement["rho_projected"], "rho_projected"),
        "linear_action_closure": _finite_scalar(
            measurement["linear_action_closure"], "linear_action_closure"
        ),
        "complement_optimality": _finite_scalar(
            measurement["complement_optimality"], "complement_optimality"
        ),
        "alpha": _pair(measurement["alpha"], "alpha"),
        "omega": _pair(measurement["omega"], "omega"),
        "projection_denominator": _pair(
            measurement["projection_denominator"], "projection_denominator"
        ),
        "local_exact_shifted_action_count": measurement.get(
            "local_exact_shifted_action_count"
        ),
        "action_counts": {key: int(value) for key, value in actions.items()},
        "rhs_sha256": measurement.get("rhs_sha256"),
        "final_correction_sha256": measurement.get("final_correction_sha256"),
        "final_action_sha256": measurement.get("final_action_sha256"),
        "final_residual_sha256": measurement.get("final_residual_sha256"),
    }
    if not all(isinstance(result[key], str) and len(result[key]) == 64 for key in (
        "rhs_sha256",
        "final_correction_sha256",
        "final_action_sha256",
        "final_residual_sha256",
    )):
        raise ValueError("W13A projected measurement hashes are incomplete")
    if result["local_exact_shifted_action_count"] != 1:
        raise ValueError("W13A local shifted action count is not fixed")
    return result


def run_w13a_projected_range_measurements(
    residuals: Mapping[str, np.ndarray],
    apply_with_measurement: Callable[[np.ndarray], tuple[np.ndarray, Mapping[str, Any]]],
    *,
    beta: float,
) -> dict[str, Any]:
    """Measure one fixed projected-range beta on the two frozen residuals.

    The callback is the existing ``H2BM6BProjectedRangePC`` diagnostic apply.
    Each residual is applied twice: the first result is the reported value and
    the second is a deterministic repeat.  No vector is retained in the JSON
    result.
    """

    if beta not in (0.5, 1.0) or tuple(residuals) != W13A_RESIDUAL_ORDER:
        raise ValueError("W13A beta or residual order is not fixed")
    started = time.perf_counter()
    measurements: dict[str, dict[str, Any]] = {}
    all_finite = True
    all_repeat = True
    all_closure = True
    total_counts = {
        "local_apply": 0,
        "physical_outer_action": 0,
        "range_apply": 0,
        "local_exact_shifted_action_count": 0,
    }
    for name in W13A_RESIDUAL_ORDER:
        rhs = np.asarray(residuals[name])
        if rhs.dtype != np.dtype(np.complex128) or rhs.ndim != 1 or not np.all(np.isfinite(rhs)):
            raise ValueError(f"W13A residual is invalid: {name}")
        first_started = time.perf_counter()
        first_correction, first_measurement = apply_with_measurement(rhs)
        first_wall = time.perf_counter() - first_started
        repeat_started = time.perf_counter()
        second_correction, second_measurement = apply_with_measurement(rhs)
        repeat_wall = time.perf_counter() - repeat_started
        first = _measurement_record(first_measurement)
        second = _measurement_record(second_measurement)
        correction_a = np.asarray(first_correction)
        correction_b = np.asarray(second_correction)
        repeat_error = float(
            np.linalg.norm(correction_a - correction_b)
            / max(float(np.linalg.norm(correction_a)), np.finfo(float).tiny)
        )
        repeat_exact = bool(
            correction_a.dtype == np.dtype(np.complex128)
            and correction_b.dtype == np.dtype(np.complex128)
            and np.array_equal(correction_a, correction_b)
            and first == second
        )
        closure_pass = first["linear_action_closure"] <= W13A_CLOSURE_LIMIT
        all_finite = all_finite and first["finite"] and second["finite"]
        all_repeat = bool(
            all_repeat and repeat_exact and bool(np.isfinite(repeat_error))
        )
        all_closure = all_closure and closure_pass
        for key in ("local_apply", "physical_outer_action", "range_apply"):
            total_counts[key] += first["action_counts"][key] + second["action_counts"][key]
        total_counts["local_exact_shifted_action_count"] += (
            first["local_exact_shifted_action_count"]
            + second["local_exact_shifted_action_count"]
        )
        measurements[name] = {
            **first,
            "repeat": second,
            "repeat_exact": repeat_exact,
            "repeat_relative_error": repeat_error,
            "closure_pass": closure_pass,
            "first_apply_wall_seconds": float(first_wall),
            "repeat_apply_wall_seconds": float(repeat_wall),
            "apply_wall_seconds": float(first_wall + repeat_wall),
        }
    checks = {
        "fixed_beta": beta in (0.5, 1.0),
        "residual_set": True,
        "finite": all_finite,
        "repeat_exact": all_repeat,
        "action_closure": all_closure,
        "local_exact_shifted_action_count": (
            total_counts["local_exact_shifted_action_count"] == 4
        ),
    }
    gate = {
        "pass": bool(all(checks.values())),
        "checks": checks,
        "problems": [key for key, value in checks.items() if not value],
    }
    return {
        "schema": W13A_SCHEMA,
        "beta": float(beta),
        "residual_order": list(W13A_RESIDUAL_ORDER),
        "measurements": measurements,
        "action_counts": total_counts,
        "gate": gate,
        "elapsed_wall_seconds": float(time.perf_counter() - started),
    }
