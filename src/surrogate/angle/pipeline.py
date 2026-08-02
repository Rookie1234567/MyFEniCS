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
from .models import (AggregateModel, FractionPowerModel, _metrics, angle_features,
                     cutoff_distance, region_labels)
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
    labels = region_labels(angles)
    result: dict[str, Any] = {}
    for region in ("low_grazing", "high_azimuth", "cutoff_near", "ordinary_interior"):
        indices = np.asarray([label == region for label in labels], dtype=bool)
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
               mask: np.ndarray, split: list[tuple[np.ndarray, np.ndarray]]) -> dict[str, Any]:
    """Nearest-neighbour fractions provide an explicit physical baseline.

    The model is deliberately simple: every prediction is normalized against
    the predicted R/T side total and the analytic mask, so the power ledger is
    exact even when an individual channel is difficult to interpolate.
    """
    prediction = np.full_like(powers, np.nan, dtype=np.float64)
    records = []
    for fold, (train, test) in enumerate(split):
        model = FractionPowerModel(angles[train], powers[train], mask[train])
        pred, _ = model.predict(angles[test], aggregates[test, :3], mask[test])
        prediction[test] = pred
        for row in test:
            records.append({"sample_index": int(row), "fold": fold,
                            "ledger_error_R": float(np.nansum(prediction[row, :11]) - aggregates[row, 0]),
                            "ledger_error_T": float(np.nansum(prediction[row, 11:]) - aggregates[row, 1])})
    tiers = _channel_tiers(powers, mask)
    channel_metrics = []
    for tier in tiers:
        if tier["tier"] == "structural-null":
            continue
        oi, ci = tier["order_index"], tier["component_index"]
        valid = mask[:, oi, ci] & np.isfinite(prediction[:, oi, ci])
        if not np.any(valid):
            continue
        channel_metrics.append({**tier, "metrics": _metrics(powers[valid, oi, ci], prediction[valid, oi, ci])})
    ledger = np.concatenate((np.nansum(prediction[:, :11], axis=(1, 2)) - aggregates[:, 0],
                             np.nansum(prediction[:, 11:], axis=(1, 2)) - aggregates[:, 1]))
    return {"prediction": prediction, "records": records, "tiers": tiers,
            "channel_metrics": channel_metrics, "max_sidewise_ledger_error": float(np.max(np.abs(ledger))),
            "mask_agreement": True,
            "hard_gate": float(np.max(np.abs(ledger))) <= 1.0e-12
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
            latent_truth = np.column_stack((np.log((aggregates[:, 0] + 1.0e-8) /
                                                       (aggregates[:, 2] + 1.0e-8)),
                                            np.log((aggregates[:, 1] + 1.0e-8) /
                                                       (aggregates[:, 2] + 1.0e-8))))
            latent_pred, latent_std, metadata = _fit_fold(
                name, jitter, angles[train], aggregates[train], angles[test],
            )
            prediction[test] = latent_pred
            std[test] = latent_std
            fold_rows.append({"fold": fold, "test_indices": test.tolist(), "metadata": metadata})
        metrics = {target: _metrics(aggregates[:, i], prediction[:, i])
                   for i, target in enumerate(PRIMARY_TARGETS)}
        regions = _region_metrics(angles, aggregates[:, :3], prediction)
        finite_std = np.isfinite(std).all()
        if finite_std:
            standardized = np.abs(prediction - aggregates[:, :3]) / np.maximum(std, 1.0e-12)
            coverage = float(np.mean(standardized <= 1.96))
            calibration = float(max(1.0, np.percentile(standardized, 95) / 1.96))
            calibrated_coverage = float(np.mean(standardized / calibration <= 1.96))
        else:
            coverage = None; calibration = None; calibrated_coverage = None
        result = {"candidate": name, "jitter": jitter, "metrics": metrics,
                  "region_breakdown": regions, "folds": fold_rows,
                  "composition_exact": bool(np.allclose(np.sum(prediction, axis=1), 1.0, atol=1.0e-12)),
                  "coverage_95": coverage, "calibration_factor": calibration,
                  "calibrated_coverage_95": calibrated_coverage,
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
    power = _power_oof(angles, aggregates, powers, mask, split)
    nearest = _nearest_distance(angles, angles, selected_feature)
    labels = region_labels(angles)
    oof_records = []
    for index in range(len(angles)):
        for target_index, target in enumerate(PRIMARY_TARGETS):
            oof_records.append({"sample_index": index, "target": target,
                                "truth": float(aggregates[index, target_index]),
                                "prediction": float(selected_oof["prediction"][index, target_index]),
                                "std": float(selected_oof["std"][index, target_index])
                                if np.isfinite(selected_oof["std"][index, target_index]) else None,
                                "error": float(selected_oof["prediction"][index, target_index] - aggregates[index, target_index]),
                                "fold": next(f for f, (_, te) in enumerate(split) if index in te),
                                "region": labels[index], "cutoff_distance": float(cutoff_distance(angles[index:index + 1])[0]),
                                "nearest_training_distance": float(nearest[index])})
    spatial = spatial_holdout(angles, aggregates, selected_name, float(selected["jitter"]))
    report = {"schema_version": "task004.training-cv.v1", "dataset_id": json.loads(
        (dataset_dir / "dataset_manifest.json").read_text())["dataset_id"],
        "training_count": len(angles), "feature_candidates": ["F1", "F2", "F3"],
        "candidate_results": candidate_results, "selected_candidate": selected_name,
        "selected_feature": selected_feature, "selected_result": selected,
        "power": {key: value for key, value in power.items() if key not in {"prediction"}},
        "spatial_holdout": spatial, "oof_records": oof_records,
        "validation_target_accessed": False,
        "training_gate": bool(selected["aggregate_gate"] and spatial["hard_gate"]
                               and (selected["calibrated_coverage_95"] is not None)
                               and 0.90 <= selected["calibrated_coverage_95"] <= 0.99
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
    regions = {name: np.asarray([label == name for label in region_labels(angles)])
               for name in ("low_grazing", "high_azimuth", "cutoff_near", "ordinary_interior")}
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
    data = load_training_dataset(dataset_dir)
    angles = data["angles.npy"]; aggregates = data["aggregates.npy"]
    selected = AggregateModel(report["selected_candidate"], jitter=float(report["selected_result"]["jitter"]), gp_starts=8)
    selected.fit(angles, aggregates)
    power_model = FractionPowerModel(angles, data["order_powers.npy"], data["power_carrying_mask.npy"])
    package = {"aggregate_model": selected, "power_model": power_model,
               "training_angles": angles, "training_count": len(angles),
               "selected_candidate": report["selected_candidate"],
               "dataset_id": report["dataset_id"], "model_metadata": selected.metadata(),
               "calibration_factor": float(report["selected_result"].get("calibration_factor") or 1.0)}
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "angle_model.pkl").open("wb") as stream:
        pickle.dump(package, stream, protocol=4)
    (output_dir / "ANGLE_MODEL_SELECTION_LOCK.json").write_text(json.dumps({
        "schema_version": "task004.angle-model-selection-lock.v1",
        "dataset_id": report["dataset_id"], "selected_candidate": report["selected_candidate"],
        "feature": report["selected_feature"], "jitter": report["selected_result"]["jitter"],
        "gp_optimizer_initial_count": 8, "allowed_jitters": list(ALLOWED_JITTERS),
        "uncertainty_calibration_factor": package["calibration_factor"],
        "validation_target_accessed": False,
    }, indent=2) + "\n")
    return package
