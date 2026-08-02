"""Training-only Task004 angle CV, spatial holdout and lock orchestration."""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np

from ..folds import FOLD_SEED, folds
from ..physics import reconstruct_aggregates
from .design import cutoff_distance as design_cutoff_distance
from .models import (
    AggregateModel, MaskedFractionPowerModel, _metrics, analytic_power_carrying_mask,
    angle_features, cutoff_distance, region_masks, region_labels,
)
from .dataset import load_training_dataset


ALLOWED_JITTERS = (1.0e-10, 1.0e-8, 1.0e-6)
PRIMARY_TARGETS = ("R_total", "T_total", "A_balance")


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def _fit_fold(name: str, jitter: float, train_x: np.ndarray, train_y: np.ndarray,
              test_x: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    model = AggregateModel(name, jitter=jitter, gp_starts=8).fit(train_x, train_y)
    mean, std = model.predict(test_x, return_std=True)
    return mean, std, model.metadata()


def _region_metrics(angles: np.ndarray, truth: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    masks = region_masks(angles)
    result: dict[str, Any] = {}
    for region in ("low_grazing", "high_azimuth", "cutoff_near", "ordinary_interior"):
        indices = masks[region]
        if not np.any(indices):
            result[region] = {"n": 0, "status": "not_present"}
        else:
            result[region] = {target: _metrics(truth[indices, i], prediction[indices, i])
                              for i, target in enumerate(PRIMARY_TARGETS)}
    return result


def _aggregate_gate(metrics: dict[str, Any], regions: dict[str, Any]) -> bool:
    for target in PRIMARY_TARGETS:
        item = metrics[target]
        if item["nrmse"] > 0.01 or item["p95_abs"] > 0.01 or item["max_abs"] > 0.03:
            return False
    for values in regions.values():
        if values.get("status") == "not_present":
            continue
        if any(values[target]["p95_abs"] > 0.02 for target in PRIMARY_TARGETS):
            return False
    return True


def _nearest_distance(query: np.ndarray, training: np.ndarray, candidate: str) -> np.ndarray:
    xq = angle_features(query, candidate); xt = angle_features(training, candidate)
    if len(xt) == 0:
        return np.full(len(xq), np.nan)
    return np.min(np.linalg.norm(xq[:, None, :] - xt[None, :, :], axis=2), axis=1)


def _channel_tiers(powers: np.ndarray, mask: np.ndarray) -> list[dict[str, Any]]:
    tiers = []
    for order in range(powers.shape[1]):
        for component in range(powers.shape[2]):
            values = powers[:, order, component][mask[:, order, component]]
            maximum = float(np.max(values)) if values.size else 0.0
            tier = "primary" if maximum >= 1.0e-3 else "secondary" if maximum >= 1.0e-6 else "structural-null"
            tiers.append({"order_index": order, "component_index": component,
                          "maximum_training_power": maximum,
                          "active_training_count": int(values.size), "tier": tier})
    return tiers


def _power_oof(angles: np.ndarray, aggregates: np.ndarray, powers: np.ndarray,
               mask: np.ndarray, split: list[tuple[np.ndarray, np.ndarray]],
               *, feature: str) -> dict[str, Any]:
    """Evaluate active-channel fractions using only each fold's training truth."""
    prediction = np.full_like(powers, np.nan, dtype=np.float64)
    uncertainty = np.full_like(powers, np.nan, dtype=np.float64)
    analytic_mask = analytic_power_carrying_mask(angles)
    mask_mismatch = np.argwhere(analytic_mask != mask)
    predicted_aggregates = np.full((len(angles), 3), np.nan, dtype=np.float64)
    records = []
    for fold, (train, test) in enumerate(split):
        aggregate_model = AggregateModel(f"gp:{feature}", jitter=1.0e-8, gp_starts=8).fit(
            angles[train], aggregates[train],
        )
        aggregate_prediction, aggregate_std = aggregate_model.predict(
            angles[test], return_std=True,
        )
        predicted_aggregates[test] = aggregate_prediction
        model = MaskedFractionPowerModel(feature="F1").fit(
            angles[train], powers[train], analytic_mask[train],
        )
        pred, pred_std = model.predict(
            angles[test], aggregate_prediction, analytic_mask[test],
            aggregate_std=aggregate_std,
        )
        prediction[test] = pred
        uncertainty[test] = pred_std
        for local, row in enumerate(test):
            entries = []
            for order_index, component_index in zip(
                    *np.nonzero(analytic_mask[row])):
                truth_value = float(powers[row, order_index, component_index])
                predicted_value = float(prediction[row, order_index, component_index])
                std_value = float(uncertainty[row, order_index, component_index])
                entries.append({
                    "order_index": int(order_index),
                    "component_index": int(component_index),
                    "truth": truth_value,
                    "prediction": predicted_value,
                    "std": std_value,
                    "error": predicted_value - truth_value,
                })
            records.append({"sample_index": int(row), "fold": fold,
                            "truth_leakage": False,
                            "regions": [name for name, values in region_masks(angles).items()
                                        if bool(values[row])],
                            "cutoff_distance": float(cutoff_distance(angles[row:row + 1])[0]),
                            "mask_signature": [
                                [int(order_index), int(component_index)]
                                for order_index, component_index in zip(
                                    *np.nonzero(analytic_mask[row])
                                )
                            ],
                            "channels": entries,
                            "ledger_error_R": float(np.nansum(prediction[row, :11]) - aggregate_prediction[local, 0]),
                            "ledger_error_T": float(np.nansum(prediction[row, 11:]) - aggregate_prediction[local, 1])})
    tiers = _channel_tiers(powers, mask)
    channel_metrics = []
    for tier in tiers:
        if tier["tier"] == "structural-null":
            continue
        oi, ci = tier["order_index"], tier["component_index"]
        valid = mask[:, oi, ci] & np.isfinite(prediction[:, oi, ci])
        if not np.any(valid):
            continue
        channel_metrics.append({
            **tier,
            "metrics": _metrics(powers[valid, oi, ci], prediction[valid, oi, ci]),
            "uncertainty_p50": float(np.nanpercentile(uncertainty[valid, oi, ci], 50)),
            "uncertainty_p95": float(np.nanpercentile(uncertainty[valid, oi, ci], 95)),
        })
    ledger = np.concatenate((
        np.nansum(prediction[:, :11], axis=(1, 2)) - predicted_aggregates[:, 0],
        np.nansum(prediction[:, 11:], axis=(1, 2)) - predicted_aggregates[:, 1],
    ))
    return {"prediction": prediction, "records": records, "tiers": tiers,
            "channel_metrics": channel_metrics, "uncertainty": uncertainty,
            "max_sidewise_ledger_error": float(np.max(np.abs(ledger))),
            "mask_agreement": bool(mask_mismatch.size == 0),
            "mask_mismatch_indices": mask_mismatch.tolist(),
            "hard_gate": float(np.max(np.abs(ledger))) <= 1.0e-12
            and mask_mismatch.size == 0
            and all(item["metrics"]["nrmse"] <= 0.03 and item["metrics"]["p95_abs"] <= 0.01
                    for item in channel_metrics if item["tier"] == "primary")}


def run_training_cv(*, dataset_dir: Path, output_dir: Path) -> dict[str, Any]:
    data = load_training_dataset(dataset_dir)
    angles = np.asarray(data["angles.npy"], dtype=np.float64)
    aggregates = np.asarray(data["aggregates.npy"], dtype=np.float64)
    powers = np.asarray(data["order_powers.npy"], dtype=np.float64)
    mask = np.asarray(data["power_carrying_mask.npy"], dtype=bool)
    base_features = angle_features(angles, "F1")
    split = folds(base_features, n_splits=5, seed=FOLD_SEED)
    candidate_specs = [("rbf:F1", 1.0e-10)]
    candidate_specs += [(f"cheb{degree}:F1", 1.0e-10) for degree in (2, 3, 4, 5)]
    candidate_specs += [(f"gp:{feature}", jitter) for feature in ("F1", "F2", "F3")
                        for jitter in ALLOWED_JITTERS]
    candidate_results = []
    selected_oof = None
    for name, jitter in candidate_specs:
        prediction = np.full((len(angles), 3), np.nan)
        std = np.full_like(prediction, np.nan)
        fold_rows = []
        for fold, (train, test) in enumerate(split):
            fold_prediction, fold_std, metadata = _fit_fold(
                name, jitter, angles[train], aggregates[train], angles[test],
            )
            prediction[test] = fold_prediction
            std[test] = fold_std
            fold_rows.append({"fold": fold, "test_indices": test.tolist(), "metadata": metadata})
        metrics = {target: _metrics(aggregates[:, i], prediction[:, i])
                   for i, target in enumerate(PRIMARY_TARGETS)}
        regions = _region_metrics(angles, aggregates[:, :3], prediction)
        finite_std = np.isfinite(std).all()
        uncertainty_regions: dict[str, Any] = {}
        if finite_std:
            standardized = np.abs(prediction - aggregates[:, :3]) / np.maximum(std, 1.0e-12)
            coverage_by_target = np.mean(standardized <= 1.96, axis=0)
            coverage = float(np.mean(coverage_by_target))
            calibration = np.maximum(1.0, np.percentile(standardized, 95, axis=0) / 1.96)
            calibrated_coverage_by_target = np.mean(
                standardized / calibration[None, :] <= 1.96, axis=0,
            )
            calibrated_coverage = float(np.mean(calibrated_coverage_by_target))
            for region, region_mask in region_masks(angles).items():
                uncertainty_regions[region] = {
                    "n": int(np.sum(region_mask)),
                    "uncalibrated_coverage_95": (
                        None if not np.any(region_mask) else [
                            float(np.mean(standardized[region_mask, index] <= 1.96))
                            for index in range(len(PRIMARY_TARGETS))
                        ]
                    ),
                    "calibrated_coverage_95": (
                        None if not np.any(region_mask) else [
                            float(np.mean(standardized[region_mask, index] /
                                          calibration[index] <= 1.96))
                            for index in range(len(PRIMARY_TARGETS))
                        ]
                    ),
                }
        else:
            coverage = None; calibration = None; calibrated_coverage = None
        uncertainty_by_target = {}
        if finite_std:
            for index, target in enumerate(PRIMARY_TARGETS):
                standardized_target = standardized[:, index]
                uncertainty_by_target[target] = {
                    "uncalibrated_coverage_95": float(np.mean(standardized_target <= 1.96)),
                    "calibrated_coverage_95": float(
                        np.mean(standardized_target / calibration[index] <= 1.96)
                    ),
                    "calibration_factor": float(calibration[index]),
                    "standardized_residual_p50": float(np.percentile(standardized_target, 50)),
                    "standardized_residual_p90": float(np.percentile(standardized_target, 90)),
                    "standardized_residual_p95": float(np.percentile(standardized_target, 95)),
                    "standardized_residual_max": float(np.max(standardized_target)),
                }
        uncertainty_gate = bool(
            finite_std and all(
                0.90 <= float(item["uncalibrated_coverage_95"]) <= 0.99
                for item in uncertainty_by_target.values()
            )
        )
        result = {"candidate": name, "jitter": jitter, "metrics": metrics,
                  "region_breakdown": regions, "folds": fold_rows,
                  "composition_exact": bool(np.allclose(np.sum(prediction, axis=1), 1.0, atol=1.0e-12)),
                  "coverage_95": coverage,
                  "coverage_95_uncalibrated": coverage,
                  "calibration_factor": (
                      None if calibration is None else float(np.max(calibration))
                  ),
                  "calibration_factor_per_target": (
                      None if calibration is None else {
                          target: float(calibration[index])
                          for index, target in enumerate(PRIMARY_TARGETS)
                      }
                  ),
                  "calibrated_coverage_95": calibrated_coverage,
                  "uncertainty_by_target": uncertainty_by_target,
                  "uncertainty_region_breakdown": uncertainty_regions,
                  "uncertainty_gate": uncertainty_gate,
                  "aggregate_gate": _aggregate_gate(metrics, regions),
                  "selection_score": max(max(item["nrmse"] / 0.01, item["p95_abs"] / 0.01,
                                             item["max_abs"] / 0.03) for item in metrics.values())}
        candidate_results.append(result)
        # Candidate ranking never uses blind validation.  Prefer lower gate
        # score, then deterministic candidate name.
        candidate_oof = {"prediction": prediction, "std": std, "folds": fold_rows}
        if selected_oof is None or (result["selection_score"], name) < (
                selected_oof["result"]["selection_score"], selected_oof["result"]["candidate"]):
            selected_oof = {"result": result, **candidate_oof}
    if selected_oof is None:
        raise RuntimeError("Task004 candidate comparison produced no model")
    selected = selected_oof["result"]
    selected_name = selected["candidate"]
    selected_feature = selected_name.split(":")[-1]
    power = _power_oof(
        angles, aggregates, powers, mask, split, feature=selected_feature,
    )
    nearest = np.full(len(angles), np.nan, dtype=np.float64)
    for train, test in split:
        nearest[test] = _nearest_distance(angles[test], angles[train], selected_feature)
    labels = region_labels(angles)
    masks = region_masks(angles)
    fold_for_index = {
        int(index): fold for fold, (_, test) in enumerate(split) for index in test
    }
    oof_records = []
    for index in range(len(angles)):
        for target_index, target in enumerate(PRIMARY_TARGETS):
            oof_records.append({"sample_index": index, "target": target,
                                "truth": float(aggregates[index, target_index]),
                                "prediction": float(selected_oof["prediction"][index, target_index]),
                                "std": float(selected_oof["std"][index, target_index])
                                if np.isfinite(selected_oof["std"][index, target_index]) else None,
                                "error": float(selected_oof["prediction"][index, target_index] - aggregates[index, target_index]),
                                "fold": fold_for_index[index],
                                "region": labels[index],
                                "regions": [name for name, region_mask in masks.items()
                                            if bool(region_mask[index])],
                                "cutoff_distance": float(cutoff_distance(angles[index:index + 1])[0]),
                                "nearest_training_distance": float(nearest[index])})
    spatial = spatial_holdout(angles, aggregates, selected_name, float(selected["jitter"]))
    manifest = json.loads((dataset_dir / "dataset_manifest.json").read_text())
    dataset_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(dataset_dir.iterdir()) if path.is_file()
    }
    report = {"schema_version": "task004.training-cv.v2", "dataset_id": manifest["dataset_id"],
        "source_sha": manifest.get("source_sha"),
        "dataset_file_hashes": dataset_hashes,
        "training_count": len(angles), "feature_candidates": ["F1", "F2", "F3"],
        "candidate_results": candidate_results, "selected_candidate": selected_name,
        "selected_feature": selected_feature, "selected_result": selected,
        "power": {key: value for key, value in power.items()
                  if key not in {"prediction", "uncertainty"}},
        "power_oof_records": power["records"],
        "spatial_holdout": spatial, "oof_records": oof_records,
        "validation_target_accessed": False,
        "training_gate": bool(selected["aggregate_gate"] and spatial["hard_gate"]
                               and selected["uncertainty_gate"]
                               and power["hard_gate"]),
        "allowed_jitters": list(ALLOWED_JITTERS),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    oof = report.pop("oof_records")
    (output_dir / "training_cv.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    (output_dir / "training_cv_oof.json").write_text(json.dumps({"records": oof}, indent=2) + "\n")
    return report


def spatial_holdout(angles: np.ndarray, aggregates: np.ndarray,
                    candidate: str, jitter: float) -> dict[str, Any]:
    regions = region_masks(angles)
    result = {}
    for name, holdout in regions.items():
        train = ~holdout
        if int(np.sum(holdout)) < 2 or int(np.sum(train)) < 8:
            result[name] = {"status": "insufficient_support", "n": int(np.sum(holdout))}
            continue
        model = AggregateModel(candidate, jitter=jitter, gp_starts=8).fit(angles[train], aggregates[train])
        prediction = model.predict(angles[holdout])
        metrics = {target: _metrics(aggregates[holdout, i], prediction[:, i])
                   for i, target in enumerate(PRIMARY_TARGETS)}
        result[name] = {"status": "measured", "n": int(np.sum(holdout)), "metrics": metrics}
    hard = all(values.get("status") == "measured" and
               all(values["metrics"][target]["p95_abs"] <= 0.02 for target in PRIMARY_TARGETS)
               for values in result.values())
    return {"regions": result, "hard_gate": bool(hard), "candidate": candidate}


def fit_final_model(dataset_dir: Path, report: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    if report.get("validation_target_accessed") is not False:
        raise RuntimeError("Task004 model lock refuses any validation-target access")
    if not bool(report.get("training_gate")):
        raise RuntimeError("Task004 model lock requires training_gate=true")
    if not bool(report.get("spatial_holdout", {}).get("hard_gate")):
        raise RuntimeError("Task004 model lock requires spatial_holdout_gate=true")
    if not bool(report.get("power", {}).get("hard_gate")):
        raise RuntimeError("Task004 model lock requires power_gate=true")
    data = load_training_dataset(dataset_dir)
    angles = data["angles.npy"]; aggregates = data["aggregates.npy"]
    selected = AggregateModel(report["selected_candidate"], jitter=float(report["selected_result"]["jitter"]), gp_starts=8)
    selected.fit(angles, aggregates)
    power_model = MaskedFractionPowerModel(feature=report["selected_feature"]).fit(
        angles, data["order_powers.npy"], analytic_power_carrying_mask(angles),
    )
    manifest = json.loads((dataset_dir / "dataset_manifest.json").read_text())
    package = {"aggregate_model": selected, "power_model": power_model,
               "training_angles": angles, "training_count": len(angles),
               "selected_candidate": report["selected_candidate"],
               "dataset_id": report["dataset_id"], "source_sha": report.get("source_sha"),
               "model_metadata": selected.metadata(), "power_model_metadata": power_model.metadata(),
               "calibration_factor": float(report["selected_result"].get("calibration_factor") or 1.0)}
    manifest_file_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(dataset_dir.iterdir())
        if path.is_file() and path.name not in {"file_hashes.json"}
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "angle_model.pkl").open("wb") as stream:
        pickle.dump(package, stream, protocol=4)
    (output_dir / "ANGLE_MODEL_SELECTION_LOCK.json").write_text(json.dumps({
        "schema_version": "task004.angle-model-selection-lock.v1",
        "dataset_id": report["dataset_id"], "source_sha": report.get("source_sha"),
        "dataset_file_hashes": report.get("dataset_file_hashes", {}),
        "training_tuple_sha256": manifest.get("train_tuple_sha256"),
        "solver_workspace_identity": manifest.get("solver_workspace_identity"),
        "config_hashes": manifest.get("config_hashes", []),
        "topology_hashes": manifest.get("topology_hashes", []),
        "selected_candidate": report["selected_candidate"],
        "feature": report["selected_feature"], "jitter": report["selected_result"]["jitter"],
        "gp_optimizer_initial_count": 8, "allowed_jitters": list(ALLOWED_JITTERS),
        "fold_seed": FOLD_SEED,
        "optimization_seeds": [
            gp_model.get("random_state")
            for fold_row in report["selected_result"].get("folds", [])
            for gp_model in fold_row.get("metadata", {}).get("models", [])
            if gp_model.get("random_state") is not None
        ],
        "uncertainty_calibration_factor": package["calibration_factor"],
        "uncertainty_by_target": report["selected_result"].get("uncertainty_by_target", {}),
        "power_model": power_model.metadata(),
        "training_code_sha": report.get("source_sha"),
        "dataset_file_hashes_recomputed": manifest_file_hashes,
        "training_gate": True, "spatial_holdout_gate": True, "power_gate": True,
        "validation_target_accessed": False,
    }, indent=2) + "\n")
    return package
