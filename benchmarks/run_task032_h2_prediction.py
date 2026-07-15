from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    summary_path = path if path.is_absolute() else ROOT / path
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    record_path = ROOT / summary["solver_record"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    return summary, record


def _factor_estimate_gib(summary: dict[str, Any]) -> float:
    inventory = summary["object_payload_ledger"][
        "local_or_augmented_factor_inventory"
    ]
    total = 0.0
    for item in inventory.values():
        stats = (item or {}).get("matrix_stats") or {}
        total += float(stats.get("matrix_memory_estimate_bytes") or 0.0)
    return total / (1024.0**3)


def _power_extrapolate(y5: float, y3: float, target_h: float = 2.0) -> tuple[float, float]:
    exponent = math.log(y3 / y5) / math.log(5.0 / 3.0)
    return y3 * (3.0 / target_h) ** exponent, exponent


def _upper(center: float) -> float:
    return center + max(0.10, 0.15 * center)


def _predict_pair(
    h5_summary: dict[str, Any],
    h5_record: dict[str, Any],
    h3_summary: dict[str, Any],
    h3_record: dict[str, Any],
) -> dict[str, Any]:
    rss5 = float(h5_summary["memory"]["max_simultaneous_worker_rss_gib"])
    rss3 = float(h3_summary["memory"]["max_simultaneous_worker_rss_gib"])
    resolution_center, resolution_exponent = _power_extrapolate(rss5, rss3)

    factor5 = _factor_estimate_gib(h5_summary)
    factor3 = _factor_estimate_gib(h3_summary)
    factor2, factor_exponent = _power_extrapolate(factor5, factor3)
    slope = (rss3 - rss5) / (factor3 - factor5)
    intercept = rss5 - slope * factor5
    factor_center = intercept + slope * factor2

    time5 = float(h5_record["timing_seconds_max_rank"]["total"])
    time3 = float(h3_record["timing_seconds_max_rank"]["total"])
    time2, time_exponent = _power_extrapolate(time5, time3)
    methods = {
        "mesh_resolution_power_law": {
            "center_gib": resolution_center,
            "conservative_upper_gib": _upper(resolution_center),
            "observed_scaling_exponent": resolution_exponent,
            "independent_variable": "target mesh spacing h",
        },
        "mumps_factor_payload_affine": {
            "center_gib": factor_center,
            "conservative_upper_gib": _upper(factor_center),
            "projected_factor_payload_gib": factor2,
            "factor_payload_scaling_exponent": factor_exponent,
            "rss_per_factor_payload_slope": slope,
            "rss_intercept_gib": intercept,
            "independent_variable": "MUMPS factor nnz payload estimate",
        },
    }
    return {
        "solver_path": h5_summary["solver_path"],
        "observations": {
            "h5_worker_rss_gib": rss5,
            "h3_worker_rss_gib": rss3,
            "h5_factor_payload_gib": factor5,
            "h3_factor_payload_gib": factor3,
            "h5_total_seconds": time5,
            "h3_total_seconds": time3,
            "h5_no_swap": h5_summary["no_swap"],
            "h3_no_swap": h3_summary["no_swap"],
            "h5_numeric_pass": h5_summary["numeric_pass"],
            "h3_numeric_pass": h3_summary["numeric_pass"],
        },
        "h2_predictions": methods,
        "h2_time_power_law": {
            "center_seconds": time2,
            "observed_scaling_exponent": time_exponent,
        },
        "two_method_center_le_4_gib": all(
            method["center_gib"] <= 4.0 for method in methods.values()
        ),
        "two_method_upper_le_5_gib": all(
            method["conservative_upper_gib"] <= 5.0
            for method in methods.values()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Task32 two-method h2 memory prediction and unlock decision."
    )
    for level in ("h5", "h3"):
        for path in ("augmented", "schur-fast", "schur-minimal"):
            parser.add_argument(f"--{level}-{path}", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    predictions = []
    for name, suffix in (
        ("augmented", "augmented"),
        ("modal-schur-fast", "schur_fast"),
        ("modal-schur-memory-minimal", "schur_minimal"),
    ):
        h5 = _load(getattr(args, f"h5_{suffix}"))
        h3 = _load(getattr(args, f"h3_{suffix}"))
        prediction = _predict_pair(*h5, *h3)
        if prediction["solver_path"] != name:
            raise SystemExit(
                f"Expected {name}, received {prediction['solver_path']} in supplied records."
            )
        predictions.append(prediction)
    eligible = [
        item
        for item in predictions
        if item["observations"]["h5_numeric_pass"]
        and item["observations"]["h3_numeric_pass"]
        and item["observations"]["h5_no_swap"]
        and item["observations"]["h3_no_swap"]
    ]
    selected = min(eligible, key=lambda item: item["observations"]["h3_worker_rss_gib"])
    unlock = bool(
        selected["two_method_center_le_4_gib"]
        and selected["two_method_upper_le_5_gib"]
    )
    output = {
        "schema_version": 1,
        "benchmark_id": "task032_h2_two_method_memory_prediction",
        "status": "h2_memory_gate_pass" if unlock else "h2_remains_locked",
        "target": {
            "h_nm": 2.0,
            "center_limit_gib": 4.0,
            "conservative_upper_limit_gib": 5.0,
            "warning_gib": 4.5,
            "controlled_termination_gib": 6.0,
        },
        "predictions": predictions,
        "selected_solver_path": selected["solver_path"],
        "h2_unlock": unlock,
        "decision": (
            "All memory prediction gates pass; h2 may run only from clean source with zero-swap watchdog."
            if unlock
            else "Do not run h2: at least one mandatory center/upper memory prediction gate failed."
        ),
    }
    path = args.output if args.output.is_absolute() else ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Task32 h2 prediction: {path}")
    print(f"Task32 h2 status: {output['status']}")


if __name__ == "__main__":
    main()
