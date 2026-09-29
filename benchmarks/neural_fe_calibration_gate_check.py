"""Recompute calibration Gates from raw compact fields; no FE or solver."""

import math

from benchmarks.neural_fe_gate_check import check_report


def check_equivalence(record):
    rows = []
    for state in record["states"]:
        pairs = {}
        for name, value in state["comparisons"].items():
            absolute, norm = value["absolute"], value["reference_norm"]
            passed = (
                math.isfinite(absolute)
                and math.isfinite(norm)
                and absolute >= 0
                and norm >= 0
            )
            passed &= absolute <= (1e-10 * norm if norm > 1e-12 else 1e-12)
            pairs[name] = bool(passed)
        directions = []
        for direction in state["finite_difference"] or []:
            exact = direction["analytic"]
            errors = [
                abs(sample["finite_difference"] - exact) / max(abs(exact), 1e-12)
                for sample in direction["samples"]
            ]
            directions.append(
                any(
                    errors[i] <= 1e-5 and errors[i + 1] <= 1e-5
                    for i in range(len(errors) - 1)
                )
            )
        nonzero = state["state"] == "ZERO_INITIALIZATION" or all(
            value > 0 for value in state["gradient_block_norms"].values()
        )
        rows.append(
            dict(
                state=state["state"],
                pairs=pairs,
                finite_difference_stable=directions,
                passed=bool(all(pairs.values()) and all(directions) and nonzero),
            )
        )
    cache = record["cache"]
    capacity = (
        cache["new_persistent_cache_bytes"] <= 512 * 2**20
        and cache["all_points_retained"]
    )
    return dict(
        status="PASS" if capacity and all(row["passed"] for row in rows) else "FAIL",
        states=rows,
        capacity_pass=bool(capacity),
        recorded_status_trusted=False,
    )


def check_scaled_verification(record):
    result = check_report(record)
    name = "FE-LSQR-COLUMN-SCALED"
    scattered = record["physics"]["rows"][name]["scattered_FE_L2_relative"]
    scattered_pass = math.isfinite(scattered) and 0 <= scattered <= 1e-4
    result["strict_scattered_pass"] = bool(scattered_pass)
    result["strict_status"] = (
        "SAME_DISCRETE_QUALIFIED"
        if scattered_pass
        and result["routes"][name]["status"] == "SAME_DISCRETE_QUALIFIED"
        else "NOT_QUALIFIED"
    )
    return result
