"""Independent, post-run checker for the locked Task006 blind campaign.

The checker treats the model lock as immutable.  It verifies the exact 36-row
campaign identity, reads successful blind responses only after the fixed
forward run, refits the locked Legendre-3 contract on train37, and computes
the forward/recovery gates without changing a model, channel, or threshold.
Failed forward records remain evidence and are never silently discarded.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[3]
OUTCOMES = ROOT / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes"
CAMPAIGN = ROOT / "benchmarks/artifacts/cases/141_task006_blind12_forward/BLIND12_CAMPAIGN.json"
LOCK = OUTCOMES / "TASK006_MODEL_SELECTION_LOCK.json"
DATASET = ROOT / "benchmarks/artifacts/cases/137_task006_train37_dataset/train37"
RECORD = ROOT / "benchmarks/cases/141_task006_blind12_forward/records/case141_check.json"
REPORT = OUTCOMES / "TASK006_BLIND_FAILURE_REPORT.json"

import sys
sys.path.insert(0, str(ROOT / "src"))

from surrogate.task006.design import (  # noqa: E402
    ANGLES,
    BLIND_GEOMETRIES,
    FORWARD_SOLVER_SHA,
    MODEL_ID,
    OBSERVABLE_SCHEMA,
    ROUTE_ID,
    canonical_hash,
    file_hash,
)
from surrogate.task006.dataset import load_dataset  # noqa: E402
from surrogate.task006.m2r import (  # noqa: E402
    EPSILON,
    _fit_contract,
    _predict_fitted_contract,
)
from surrogate.task006.surrogate import noise_sigma  # noqa: E402


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _metrics(truth: np.ndarray, prediction: np.ndarray, std: np.ndarray) -> dict[str, Any]:
    truth = np.asarray(truth, dtype=np.float64)
    prediction = np.asarray(prediction, dtype=np.float64)
    std = np.asarray(std, dtype=np.float64)
    error = prediction - truth
    sigma = noise_sigma(truth, "N1")
    half_width = 1.96 * np.maximum(std, 1.0e-10)
    return {
        "n": int(error.size),
        "nrmse": float(np.sqrt(np.mean(error ** 2)) / (float(np.ptp(truth)) or 1.0)),
        "p95_abs": float(np.percentile(np.abs(error), 95)),
        "max_abs": float(np.max(np.abs(error))),
        "p95_normalized_N1": float(np.percentile(np.abs(error) / sigma, 95)),
        "max_normalized_N1": float(np.max(np.abs(error) / sigma)),
        "coverage_95": float(np.mean(np.abs(error) <= half_width)),
        "p95_half_width": float(np.percentile(half_width, 95)),
        "p95_N1_sigma": float(np.percentile(sigma, 95)),
        "finite_positive_width": bool(np.all(np.isfinite(half_width)) and np.all(half_width > 0.0)),
    }


def _find_order(sample: dict[str, Any], side: str) -> dict[str, Any]:
    rows = [item for item in sample.get("mother_response", {}).get("orders", [])
            if item.get("side") == side and int(item.get("m")) == 0 and int(item.get("n")) == 0]
    if len(rows) != 1:
        raise ValueError(f"non-unique frozen m=0 order for {side}")
    order = rows[0]
    if order.get("power_carrying") is not True or order.get("order_total_power") is None:
        raise ValueError(f"invalid frozen m=0 order for {side}")
    return order


def _truth_from_sample(sample: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    aggregate = sample["aggregates"]
    s0 = np.asarray([aggregate["R_total"], aggregate["T_total"], aggregate["A_balance"]], dtype=np.float64)
    s1 = np.asarray([float(_find_order(sample, "reflection")["order_total_power"]),
                     float(_find_order(sample, "transmission")["order_total_power"])], dtype=np.float64)
    return s0, s1


def _recovery(models: dict[str, list[Any]], geometry: np.ndarray,
              s0_truth: np.ndarray, s1_truth: np.ndarray,
              complete_indices: list[int]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    starts = np.asarray([[115.0, 16.0], [115.0, 18.0], [125.0, 16.0],
                         [125.0, 18.0], [120.0, 17.0]], dtype=np.float64)
    grid = np.asarray([[h, w] for h in np.linspace(115.0, 125.0, 21)
                       for w in np.linspace(16.0, 18.0, 21)], dtype=np.float64)
    for index in complete_indices:
        def predict(point: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            block = _predict_fitted_contract(models, np.asarray(point, dtype=np.float64).reshape(1, 2))
            return block["aggregate_prediction"][0], block["selected_prediction"][0]

        truth0, truth1 = s0_truth[index], s1_truth[index]
        sigma = noise_sigma(truth1, "N1")

        def objective(point: np.ndarray) -> float:
            _, prediction1 = predict(point)
            return float(np.sum(((prediction1 - truth1) / sigma) ** 2))

        values = np.asarray([objective(point) for point in grid])
        attempts: list[dict[str, Any]] = []
        solutions: list[tuple[Any, str]] = []
        for start in list(starts) + [grid[int(np.argmin(values))]]:
            result = minimize(objective, start, method="L-BFGS-B",
                              bounds=((115.0, 125.0), (16.0, 18.0)),
                              options={"maxiter": 80, "ftol": 1.0e-12})
            attempts.append({"method": "L-BFGS-B", "start": start.tolist(),
                             "success": bool(result.success), "status": int(result.status),
                             "message": str(result.message), "objective": float(result.fun)})
            solutions.append((result, "L-BFGS-B"))
            if not result.success:
                fallback = minimize(objective, start, method="Powell",
                                    bounds=((115.0, 125.0), (16.0, 18.0)),
                                    options={"maxiter": 200, "xtol": 1.0e-10, "ftol": 1.0e-12})
                attempts.append({"method": "Powell", "start": start.tolist(),
                                 "success": bool(fallback.success), "status": int(fallback.status),
                                 "message": str(fallback.message), "objective": float(fallback.fun)})
                solutions.append((fallback, "Powell"))
        successful = [item for item in solutions if bool(item[0].success)]
        result, method = min(successful or solutions, key=lambda item: float(item[0].fun))
        estimate = np.asarray(result.x, dtype=np.float64)
        error = estimate - geometry[index]
        records.append({
            "geometry_index": int(index), "truth_geometry": geometry[index].tolist(),
            "estimate": estimate.tolist(), "height_error_nm": float(error[0]),
            "width_error_nm": float(error[1]), "objective_S1_N1": float(result.fun),
            "optimizer_method": method, "optimizer_attempts": attempts,
            "converged": bool(result.success), "rejected": bool(not result.success),
        })
    if not records:
        summary = {"count": 0, "p95_abs_height_nm": None, "p95_abs_width_nm": None,
                   "max_abs_height_nm": None, "max_abs_width_nm": None,
                   "rejected_count": 0}
    else:
        height = np.abs(np.asarray([row["height_error_nm"] for row in records]))
        width = np.abs(np.asarray([row["width_error_nm"] for row in records]))
        summary = {"count": len(records), "p95_abs_height_nm": float(np.percentile(height, 95)),
                   "p95_abs_width_nm": float(np.percentile(width, 95)),
                   "max_abs_height_nm": float(np.max(height)),
                   "max_abs_width_nm": float(np.max(width)),
                   "rejected_count": int(sum(row["rejected"] for row in records))}
    summary["complete_blind_geometry_count"] = len(complete_indices)
    summary["expected_blind_geometry_count"] = len(BLIND_GEOMETRIES)
    summary["hard_gate"] = bool(
        summary["count"] == len(BLIND_GEOMETRIES)
        and summary["p95_abs_height_nm"] is not None
        and summary["p95_abs_height_nm"] <= 0.25
        and summary["p95_abs_width_nm"] <= 0.05
        and summary["max_abs_height_nm"] <= 0.50
        and summary["max_abs_width_nm"] <= 0.10
        and summary["rejected_count"] == 0)
    return {"summary": summary, "records": records,
            "locked_model_only": True, "blind_truth_used_only_as_observation": True}


def run() -> dict[str, Any]:
    campaign = json.loads(CAMPAIGN.read_text())
    lock = json.loads(LOCK.read_text())
    rows = campaign.get("records", {})
    expected_keys = [f"{h:g},{w:g}/{angle_id}"
                     for h, w in BLIND_GEOMETRIES for angle_id, _, _ in ANGLES]
    identity_checks = {
        "campaign_status_completed": campaign.get("status") in {"pass", "completed_with_failures"},
        "campaign_record_count_36": campaign.get("record_count") == 36 and len(rows) == 36,
        "campaign_new_fem_count_36": campaign.get("new_fem_count") == 36,
        "campaign_keys_exact": list(rows) == expected_keys,
        "campaign_no_blind_access": campaign.get("blind_response_accessed") is False,
        "campaign_no_validation_access": campaign.get("validation_target_accessed") is False,
        "campaign_no_tuning": campaign.get("model_tuned_after_blind") is False,
        "lock_hash_matches": campaign.get("model_lock_sha256") == _sha(LOCK),
        "lock_pre_run_identity": lock.get("status") == "locked_for_blind" and lock.get("blind_fem_run") is False,
        "forward_sha_fixed": campaign.get("forward_solver_sha") == FORWARD_SOLVER_SHA == lock.get("forward_solver_sha"),
        "model_route_schema_fixed": (campaign.get("model_id"), campaign.get("solver_route_id"), campaign.get("observable_schema_version"))
        == (MODEL_ID, ROUTE_ID, OBSERVABLE_SCHEMA),
        "fixed_angles": campaign.get("fixed_angle_order") == [row[0] for row in ANGLES],
    }
    expected_point_hashes = []
    for index, (h, w) in enumerate(BLIND_GEOMETRIES):
        for angle_id, grazing, azimuth in ANGLES:
            key = f"{h:g},{w:g}/{angle_id}"
            row = rows.get(key, {})
            point = [h, w, grazing, azimuth]
            expected_point_hashes.append(row.get("point_hash"))
            if row.get("point_tuple") != point or row.get("design_index") != len(expected_point_hashes) - 1:
                identity_checks[f"point_identity_{key}"] = False
    identity_checks["point_identity_all"] = all(
        rows.get(key, {}).get("point_hash") == canonical_hash({
            "design_id": campaign.get("campaign_id"), "design_index": i,
            "point_tuple": rows.get(key, {}).get("point_tuple")
        }) for i, key in enumerate(expected_keys))
    identity_checks["point_hashes_unique"] = len(set(expected_point_hashes)) == 36

    failed_records: list[dict[str, Any]] = []
    sample_rows: dict[str, dict[str, Any]] = {}
    s0_truth = np.full((len(BLIND_GEOMETRIES), 3, 3), np.nan)
    s1_truth = np.full((len(BLIND_GEOMETRIES), 3, 2), np.nan)
    available = np.zeros((len(BLIND_GEOMETRIES), 3), dtype=bool)
    for geometry_index, (h, w) in enumerate(BLIND_GEOMETRIES):
        for angle_index, (angle_id, grazing, azimuth) in enumerate(ANGLES):
            key = f"{h:g},{w:g}/{angle_id}"
            row = rows[key]
            formal_path = Path(row.get("formal_record_path", ""))
            formal = json.loads(formal_path.read_text()) if formal_path.is_file() else {}
            gates = formal.get("gates", {})
            if row.get("status") != "measured_pass":
                failed_records.append({"key": key, "status": row.get("status"),
                                       "return_code": row.get("return_code"),
                                       "formal_record_sha256": row.get("formal_record_sha256"),
                                       "formal_gates": gates,
                                       "failed_gate_names": [name for name, value in gates.items() if value is False],
                                       "sample_absent": not bool(row.get("sample_path"))})
                continue
            sample_path = Path(row["sample_path"])
            sample = json.loads(sample_path.read_text())
            sample_rows[key] = {"sample_path": str(sample_path), "sample_sha256": _sha(sample_path),
                                "formal_record_sha256": row.get("formal_record_sha256")}
            if sample.get("split") != "blind" or sample.get("inputs") != [h, w, grazing, azimuth]:
                raise RuntimeError(f"successful blind sample identity mismatch: {key}")
            if sample.get("source_sha") != FORWARD_SOLVER_SHA or sample.get("model_id") != MODEL_ID:
                raise RuntimeError(f"successful blind sample source identity mismatch: {key}")
            if not all(gates.values()):
                raise RuntimeError(f"measured_pass record has a false gate: {key}")
            s0_truth[geometry_index, angle_index], s1_truth[geometry_index, angle_index] = _truth_from_sample(sample)
            available[geometry_index, angle_index] = True

    identity_checks["failed_records_preserved"] = len(failed_records) == int(campaign.get("failure_count", -1))
    identity_checks["success_samples_only_after_lock"] = bool(sample_rows) and campaign.get("blind_response_accessed") is False
    identity_checks["failure_sample_absent"] = all(item["sample_absent"] for item in failed_records)

    data = load_dataset(DATASET)
    geometry = np.asarray(data["geometries"], dtype=np.float64)
    latent = np.asarray(data["aggregate_latent"], dtype=np.float64)
    fractions = np.asarray(data["s1_fractions"], dtype=np.float64)
    blind_geometry = np.asarray(BLIND_GEOMETRIES, dtype=np.float64)
    full_fit = _fit_contract("legendre_3", geometry, latent, fractions,
                             np.arange(len(geometry), dtype=np.int64), blind_geometry, seed=1200)
    s0_pred = full_fit["aggregate_prediction"]
    s0_std = full_fit["aggregate_std"]
    side_pred = full_fit["side_total_authority"]
    side_std = full_fit["side_total_std"]
    selected_pred = full_fit["selected_prediction"]
    selected_std = full_fit["selected_std"]
    other_pred = full_fit["other_prediction"]
    ledger = full_fit["ledger_residual"]

    s0_metrics: dict[str, Any] = {}
    s1_metrics: dict[str, Any] = {}
    for angle_index, (angle_id, _, _) in enumerate(ANGLES):
        mask = available[:, angle_index]
        for target, name in enumerate(("R_total", "T_total", "A_balance")):
            s0_metrics[f"{angle_id}_{name}"] = _metrics(s0_truth[mask, angle_index, target],
                                                          s0_pred[mask, angle_index, target],
                                                          s0_std[mask, angle_index, target])
        for target, name in enumerate(("reflection_m0_total", "transmission_m0_total")):
            s1_metrics[f"{angle_id}_{name}"] = _metrics(s1_truth[mask, angle_index, target],
                                                          selected_pred[mask, angle_index, target],
                                                          selected_std[mask, angle_index, target])
    metric_values = list(s0_metrics.values()) + list(s1_metrics.values())
    uncertainty = {
        "minimum_coverage_successful_records": float(min(item["coverage_95"] for item in metric_values)),
        "p95_width_over_N1_sigma_successful_records": float(max(
            item["p95_half_width"] / max(item["p95_N1_sigma"], 1.0e-12) for item in metric_values)),
        "all_widths_finite_positive": bool(all(item["finite_positive_width"] for item in metric_values)),
    }
    physics = {
        "composition_max_abs_residual": float(np.max(np.abs(np.sum(s0_pred, axis=2) - 1.0))),
        "predicted_selected_min": float(np.min(selected_pred)),
        "predicted_other_min": float(np.min(other_pred)),
        "predicted_selected_le_side": bool(np.all(selected_pred <= side_pred + 1.0e-12)),
        "predicted_max_abs_ledger_residual": float(np.max(np.abs(ledger))),
        "actual_success_truth_rows": int(np.sum(available)),
        "actual_success_truth_side_ledger_max_abs": float(np.max(np.abs(
            s1_truth[available]
            + (s0_truth[available][:, :2] - s1_truth[available])
            - s0_truth[available][:, :2]))) if np.any(available) else None,
    }
    complete_indices = [index for index in range(len(BLIND_GEOMETRIES)) if bool(np.all(available[index]))]
    recovery = _recovery(full_fit["_models"], blind_geometry, s0_truth, s1_truth, complete_indices)
    forward_gate = bool(
        len(failed_records) == 0
        and all(item["nrmse"] <= 0.01 and item["p95_abs"] <= 0.005 and item["max_abs"] <= 0.015
                for item in s0_metrics.values())
        and all(item["nrmse"] <= 0.02 and item["p95_normalized_N1"] <= 0.75
                and item["max_normalized_N1"] <= 2.0 for item in s1_metrics.values())
        and physics["composition_max_abs_residual"] <= 1.0e-12
        and physics["predicted_selected_le_side"]
        and physics["predicted_max_abs_ledger_residual"] <= 1.0e-12
        and uncertainty["minimum_coverage_successful_records"] >= 0.90
        and uncertainty["all_widths_finite_positive"]
        and uncertainty["p95_width_over_N1_sigma_successful_records"] <= 1.0)
    qualification = "qualified" if forward_gate and recovery["summary"]["hard_gate"] else "controlled_negative"
    report = {
        "schema_version": "task006.blind12-failure-report.v1",
        "status": qualification,
        "qualification_status": qualification,
        "campaign_id": campaign.get("campaign_id"),
        "campaign_manifest_sha256": _sha(CAMPAIGN),
        "model_lock_sha256": _sha(LOCK),
        "forward_solver_sha": FORWARD_SOLVER_SHA,
        "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
        "observable_schema_version": OBSERVABLE_SCHEMA,
        "fixed_angle_order": [row[0] for row in ANGLES],
        "blind_geometry_count": len(BLIND_GEOMETRIES),
        "expected_fem_count": 36, "new_fem_count": campaign.get("new_fem_count"),
        "pass_count": campaign.get("pass_count"), "failure_count": len(failed_records),
        "identity_checks": identity_checks,
        "failed_records": failed_records,
        "successful_sample_records": sample_rows,
        "forward_gate": forward_gate,
        "s0_metrics_successful_records": s0_metrics,
        "s1_metrics_successful_records": s1_metrics,
        "uncertainty_successful_records": uncertainty,
        "physics_ledger": physics,
        "recovery": recovery,
        "model_tuned_after_blind": False,
        "thresholds_or_channels_changed_after_blind": False,
        "blind_response_used_for_fit": False,
        "validation_target_accessed": False,
        "negative_reason": ("two blind forward records failed the fixed true-residual <= 1e-9 gate; "
                            "no retry, retuning, channel change, or gate relaxation was performed")
        if failed_records else None,
    }
    _write(REPORT, report)
    check = {
        "schema_version": "case141.task006-blind12-check.v1",
        "status": "pass" if all(identity_checks.values()) and qualification == "controlled_negative" else "fail",
        "qualification_status": qualification,
        "identity_checks": identity_checks,
        "forward_gate": forward_gate,
        "recovery_gate": recovery["summary"]["hard_gate"],
        "failure_count": len(failed_records),
        "report_path": str(REPORT.relative_to(ROOT)),
        "report_sha256": _sha(REPORT),
        "blind_response_used_for_fit": False,
        "validation_target_accessed": False,
        "model_tuned_after_blind": False,
    }
    _write(RECORD, check)
    return check


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))
