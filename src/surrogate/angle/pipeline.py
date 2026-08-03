"""Training-only Task004 qualification pipeline.

The module keeps the forward-data identity separate from the code used to fit
the angle model.  It deliberately has no path that opens a blind response
before a model-selection lock exists.
"""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np

from ..folds import FOLD_SEED, fold_identity, folds
from .dataset import FORWARD_SOLVER_SHA, load_training_dataset, verify_immutable_package
from .models import (
    AggregateModel,
    MaskedFractionPowerModel,
    _metrics,
    analytic_power_carrying_mask,
    angle_features,
    cutoff_distance,
    cutoff_identity,
    region_labels,
    region_masks,
)


ALLOWED_JITTERS = (1.0e-10, 1.0e-8, 1.0e-6)
PRIMARY_TARGETS = ("R_total", "T_total", "A_balance")
PRODUCTION_CANDIDATES = tuple(
    (f"gp:{feature}", jitter)
    for feature in ("F1", "F2", "F3")
    for jitter in ALLOWED_JITTERS
)
BASELINE_CANDIDATES = (("rbf:F1", 1.0e-10),) + tuple(
    (f"cheb{degree}:F1", 1.0e-10) for degree in (2, 3, 4, 5)
)


def _json_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def _fit_fold(name: str, jitter: float, train_angles: np.ndarray,
              train_y: np.ndarray, test_angles: np.ndarray
              ) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    model = AggregateModel(name, jitter=jitter, gp_starts=8).fit(
        train_angles, train_y[:, :3],
    )
    mean, std = model.predict(test_angles, return_std=True)
    return np.asarray(mean), np.asarray(std), model.metadata()


def _aggregate_gate(metrics: dict[str, Any], regions: dict[str, Any]) -> bool:
    for target in PRIMARY_TARGETS:
        item = metrics[target]
        if item["nrmse"] > 0.01 or item["p95_abs"] > 0.01 or item["max_abs"] > 0.03:
            return False
    for values in regions.values():
        if values.get("status") != "measured":
            return False
        if any(values[target]["p95_abs"] > 0.02 for target in PRIMARY_TARGETS):
            return False
    return True


def _region_metrics(angles: np.ndarray, truth: np.ndarray,
                    prediction: np.ndarray) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, indices in region_masks(angles).items():
        if not np.any(indices):
            result[name] = {"status": "not_present", "n": 0}
        else:
            result[name] = {
                "status": "measured", "n": int(np.sum(indices)),
                **{target: _metrics(truth[indices, i], prediction[indices, i])
                   for i, target in enumerate(PRIMARY_TARGETS)},
            }
    return result


def _nearest_distance(query: np.ndarray, training: np.ndarray,
                      candidate: str) -> np.ndarray:
    xq = angle_features(query, candidate)
    xt = angle_features(training, candidate)
    if not len(xt):
        return np.full(len(xq), np.nan)
    return np.min(np.linalg.norm(xq[:, None, :] - xt[None, :, :], axis=2), axis=1)


def _channel_tiers(powers: np.ndarray, mask: np.ndarray) -> list[dict[str, Any]]:
    tiers: list[dict[str, Any]] = []
    for order in range(powers.shape[1]):
        for component in range(powers.shape[2]):
            values = powers[:, order, component][mask[:, order, component]]
            maximum = float(np.max(values)) if values.size else 0.0
            tier = ("primary" if maximum >= 1.0e-3 else
                    "secondary" if maximum >= 1.0e-6 else "structural-null")
            tiers.append({"order_index": order, "component_index": component,
                          "maximum_training_power": maximum,
                          "active_training_count": int(values.size), "tier": tier})
    return tiers


def _calibrate_cross_fitted(truth: np.ndarray, prediction: np.ndarray,
                            std: np.ndarray,
                            split: list[tuple[np.ndarray, np.ndarray]],
                            angles: np.ndarray) -> dict[str, Any]:
    finite = np.isfinite(std).all()
    if not finite:
        return {"status": "not_available", "gate": False}
    raw = np.abs(prediction - truth) / np.maximum(std, 1.0e-12)
    calibrated_std = np.full_like(std, np.nan)
    fold_factors: list[dict[str, Any]] = []
    for fold, (_, test) in enumerate(split):
        other = np.concatenate([split[k][1] for k in range(len(split)) if k != fold])
        factors = np.maximum(1.0, np.percentile(raw[other], 95, axis=0) / 1.96)
        calibrated_std[test] = std[test] * factors[None, :]
        fold_factors.append({"fold": fold, "source_oof_indices": other.tolist(),
                             "factor_by_target": {target: float(factors[i])
                                                   for i, target in enumerate(PRIMARY_TARGETS)}})
    final_factors = np.maximum(1.0, np.percentile(raw, 95, axis=0) / 1.96)
    target_report: dict[str, Any] = {}
    region_report: dict[str, Any] = {}
    for i, target in enumerate(PRIMARY_TARGETS):
        raw_coverage = float(np.mean(raw[:, i] <= 1.96))
        cf_coverage = float(np.mean(np.abs(prediction[:, i] - truth[:, i]) /
                                    np.maximum(calibrated_std[:, i], 1.0e-12) <= 1.96))
        target_report[target] = {
            "raw_coverage_95": raw_coverage,
            "cross_fitted_coverage_95": cf_coverage,
            "final_factor": float(final_factors[i]),
            "standardized_residual_p50": float(np.percentile(raw[:, i], 50)),
            "standardized_residual_p95": float(np.percentile(raw[:, i], 95)),
            "standardized_residual_max": float(np.max(raw[:, i])),
        }
    for name, indices in region_masks(angles).items():
        region_report[name] = {
            "n": int(np.sum(indices)),
            "raw_coverage_95": [float(np.mean(raw[indices, i] <= 1.96))
                                 for i in range(3)] if np.any(indices) else None,
            "cross_fitted_coverage_95": [
                float(np.mean(np.abs(prediction[indices, i] - truth[indices, i]) /
                              np.maximum(calibrated_std[indices, i], 1.0e-12) <= 1.96))
                for i in range(3)
            ] if np.any(indices) else None,
        }
    gate = all(0.90 <= item["cross_fitted_coverage_95"] <= 0.99
               for item in target_report.values())
    return {"status": "cross_fitted", "gate": bool(gate),
            "fold_factors": fold_factors,
            "target": target_report, "region": region_report,
            "final_factors": {target: float(final_factors[i])
                              for i, target in enumerate(PRIMARY_TARGETS)}}


def _window_hash(indices: list[int], angles: np.ndarray) -> str:
    return _json_hash({"indices": indices,
                       "tuples": np.asarray(angles)[indices].round(12).tolist()})


def freeze_spatial_holdout_windows(*, angles: np.ndarray, output: Path,
                                   dataset_id: str,
                                   training_tuple_sha256: str) -> dict[str, Any]:
    """Freeze four finite, response-blind local windows before CV."""
    values = np.asarray(angles, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 2 or len(values) < 40:
        raise ValueError("Task004 spatial windows require the 96 angle design")
    if output.is_file():
        old = json.loads(output.read_text())
        if old.get("training_tuple_sha256") != training_tuple_sha256:
            raise ValueError("frozen spatial windows do not match training design")
        return old
    used: set[int] = set()
    windows: dict[str, list[int]] = {}

    def choose(name: str, pool: np.ndarray, center: tuple[float, float], count: int = 8) -> None:
        candidates = [int(i) for i in pool if int(i) not in used]
        distances = sorted(candidates, key=lambda i: (
            float(np.linalg.norm((values[i] - np.asarray(center)) / np.asarray([9.5, 90.0]))), i,
        ))
        chosen = distances[:count]
        if len(chosen) < 4:
            raise ValueError(f"insufficient local support for spatial window {name}")
        windows[name] = chosen
        used.update(chosen)

    region = region_masks(values)
    choose("low_grazing", np.flatnonzero(region["low_grazing"]), (1.25, 45.0))
    choose("high_azimuth", np.flatnonzero(region["high_azimuth"]), (5.25, 82.5))
    margins = angle_features(values, "F3")[:, 2:]
    abs_margin = np.min(np.abs(margins), axis=1)
    order = np.argsort(abs_margin, kind="mergesort")
    # Keep both sides of the nearest signed crossing in the finite window.
    signed_pool = [int(i) for i in order if int(i) not in used]
    signed_pool.sort(key=lambda i: (float(abs_margin[i]), i))
    positive = [i for i in signed_pool if float(margins[i, np.argmin(np.abs(margins[i]))]) >= 0]
    negative = [i for i in signed_pool if float(margins[i, np.argmin(np.abs(margins[i]))]) < 0]
    choose_cut = (positive[:4] + negative[:4])
    if len(choose_cut) < 8:
        choose_cut = signed_pool[:8]
    windows["cutoff_near"] = choose_cut[:8]
    used.update(windows["cutoff_near"])
    ordinary_pool = np.flatnonzero(region["ordinary_interior"])
    choose("ordinary_interior", ordinary_pool, (5.25, 45.0))
    payload = {
        "schema_version": "task004.spatial-holdout-windows.v1",
        "dataset_id": dataset_id,
        "training_tuple_sha256": training_tuple_sha256,
        "window_count": 4,
        "windows": [],
        "frozen_before_response_model_selection": True,
    }
    for name in ("low_grazing", "high_azimuth", "cutoff_near", "ordinary_interior"):
        indices = windows[name]
        cutoff_orders, signed = cutoff_identity(values[indices])
        payload["windows"].append({
            "name": name, "indices": indices,
            "tuples": values[indices].round(12).tolist(),
            "count": len(indices), "window_sha256": _window_hash(indices, values),
            "cutoff_orders": cutoff_orders.tolist(), "signed_cutoff_margins": signed.tolist(),
            "region_overlap": [region_name for region_name, mask in region.items()
                                if bool(np.any(mask[indices]))],
        })
    payload["windows_sha256"] = _json_hash(payload["windows"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def _load_windows(path: Path, angles: np.ndarray, training_tuple_sha256: str) -> dict[str, np.ndarray]:
    payload = json.loads(path.read_text())
    if payload.get("training_tuple_sha256") != training_tuple_sha256:
        raise ValueError("Task004 spatial window hash does not match training package")
    result = {}
    for item in payload.get("windows", []):
        indices = np.asarray(item["indices"], dtype=np.int64)
        if _window_hash(indices.tolist(), angles) != item.get("window_sha256"):
            raise ValueError(f"spatial window hash mismatch: {item.get('name')}")
        result[str(item["name"])] = indices
    if set(result) != {"low_grazing", "high_azimuth", "cutoff_near", "ordinary_interior"}:
        raise ValueError("Task004 spatial window set is incomplete")
    return result


def build_mask_topology_coverage(*, training_angles: np.ndarray,
                                 training_mask: np.ndarray,
                                 validation_design: Path,
                                 candidate_pool: Path,
                                 output: Path,
                                 dataset_id: str) -> dict[str, Any]:
    """Audit mask signatures using response-blind angle designs only."""
    if output.is_file():
        return json.loads(output.read_text())

    def design_angles(path: Path) -> np.ndarray:
        design = json.loads(path.read_text())
        return np.asarray([[float(row["grazing_deg"]), float(row["azimuth_deg"])]
                           for row in design["points"]], dtype=np.float64)

    validation = design_angles(validation_design)
    candidates = design_angles(candidate_pool)
    all_angles = np.vstack((training_angles, validation, candidates))
    authority = analytic_power_carrying_mask(all_angles)
    n_train = len(training_angles); n_val = len(validation)
    train_authority = authority[:n_train]
    val_authority = authority[n_train:n_train + n_val]
    candidate_authority = authority[n_train + n_val:]

    def signature(mask: np.ndarray) -> str:
        return ";".join(str(int(value)) for value in np.flatnonzero(mask))

    train_signatures = [signature(row) for row in train_authority]
    actual_signatures = [signature(row) for row in np.asarray(training_mask, dtype=bool)]
    counts = {key: train_signatures.count(key) for key in sorted(set(train_signatures))}
    val_counts = {key: [i for i, row in enumerate(val_authority)
                        if signature(row) == key] for key in sorted(set(signature(row) for row in val_authority))}
    candidate_counts = {key: int(sum(signature(row) == key for row in candidate_authority))
                        for key in sorted(set(signature(row) for row in candidate_authority))}
    split = folds(angle_features(training_angles, "F1"), n_splits=5, seed=FOLD_SEED)
    fold_support = []
    for fold, (train, test) in enumerate(split):
        fold_train = {train_signatures[int(i)] for i in train}
        fold_test = {train_signatures[int(i)] for i in test}
        fold_support.append({"fold": fold, "train_signatures": sorted(fold_train),
                             "test_signatures": sorted(fold_test),
                             "all_test_supported": bool(fold_test <= fold_train)})
    payload = {
        "schema_version": "task004.mask-topology-coverage.v1", "dataset_id": dataset_id,
        "training_count": n_train, "validation_count": n_val,
        "candidate_pool_count": len(candidates), "training_signature_counts": counts,
        "validation_signature_counts": {key: len(rows) for key, rows in val_counts.items()},
        "candidate_signature_counts": candidate_counts,
        "validation_unseen_signatures": sorted(set(val_counts) - set(counts)),
        "candidate_unseen_signatures": sorted(set(candidate_counts) - set(counts)),
        "fold_support": fold_support,
        "training_mask_matches_independent_authority": actual_signatures == train_signatures,
        "policy": "unsupported_mask_topology -> warning/unqualified; no nearest fraction fallback",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def _power_oof(*, angles: np.ndarray, aggregates: np.ndarray,
               powers: np.ndarray, mask: np.ndarray,
               split: list[tuple[np.ndarray, np.ndarray]],
               aggregate_candidate: str, aggregate_jitter: float,
               aggregate_prediction: np.ndarray,
               aggregate_std: np.ndarray, feature: str) -> dict[str, Any]:
    prediction = np.full_like(powers, np.nan, dtype=np.float64)
    uncertainty = np.full_like(powers, np.nan, dtype=np.float64)
    analytic_mask = analytic_power_carrying_mask(angles)
    mismatch = np.argwhere(analytic_mask != mask)
    records: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    for fold, (train, test) in enumerate(split):
        model = MaskedFractionPowerModel(feature=feature).fit(
            angles[train], powers[train], analytic_mask[train],
        )
        pred, pred_std = model.predict(
            angles[test], aggregate_prediction[test], analytic_mask[test],
            aggregate_std=aggregate_std[test],
        )
        prediction[test] = pred; uncertainty[test] = pred_std
        unsupported.extend({**item, "fold": fold} for item in model.unsupported_topologies)
        nearest = _nearest_distance(angles[test], angles[train], feature)
        cutoff_order, signed_margin = cutoff_identity(angles[test])
        for local, row in enumerate(test):
            channels = []
            for order_index, component_index in zip(*np.nonzero(analytic_mask[row])):
                pv = float(pred[local, order_index, component_index])
                sv = float(pred_std[local, order_index, component_index])
                tv = float(powers[row, order_index, component_index])
                channels.append({"order_index": int(order_index), "component_index": int(component_index),
                                 "truth": tv, "prediction": pv, "std": sv,
                                 "error": pv - tv})
            side_error = {
                "reflection": float(np.nansum(pred[local, :11]) - aggregate_prediction[row, 0]),
                "transmission": float(np.nansum(pred[local, 11:]) - aggregate_prediction[row, 1]),
            }
            records.append({"sample_index": int(row), "fold": fold,
                            "truth_leakage": False,
                            "aggregate_candidate": aggregate_candidate,
                            "aggregate_feature": feature,
                            "aggregate_jitter": aggregate_jitter,
                            "fraction_model": model.metadata(),
                            "mask_signature": [int(i) for i in np.flatnonzero(analytic_mask[row])],
                            "channels": channels, "sidewise_ledger_error": side_error,
                            "nearest_actual_fold_training_distance": float(nearest[local]),
                            "cutoff_order": int(cutoff_order[local]),
                            "signed_cutoff_margin": float(signed_margin[local]),
                            "regions": [name for name, values in region_masks(angles).items()
                                        if bool(values[row])]})
    tiers = _channel_tiers(powers, mask)
    channel_metrics = []
    for item in tiers:
        if item["tier"] == "structural-null":
            continue
        oi, ci = item["order_index"], item["component_index"]
        valid = mask[:, oi, ci] & np.isfinite(prediction[:, oi, ci])
        if not np.any(valid):
            continue
        channel_metrics.append({**item,
            "metrics": _metrics(powers[valid, oi, ci], prediction[valid, oi, ci]),
            "uncertainty_p50": float(np.nanpercentile(uncertainty[valid, oi, ci], 50)),
            "uncertainty_p95": float(np.nanpercentile(uncertainty[valid, oi, ci], 95)),
        })
    ledger = np.concatenate((
        np.nansum(prediction[:, :11], axis=(1, 2)) - aggregate_prediction[:, 0],
        np.nansum(prediction[:, 11:], axis=(1, 2)) - aggregate_prediction[:, 1],
    ))
    primary_pass = all(item["metrics"]["nrmse"] <= 0.03 and
                       item["metrics"]["p95_abs"] <= 0.01
                       for item in channel_metrics if item["tier"] == "primary")
    hard = bool(mismatch.size == 0 and not unsupported and
                float(np.max(np.abs(ledger))) <= 1.0e-12 and primary_pass)
    return {"records": records, "tiers": tiers, "channel_metrics": channel_metrics,
            "max_sidewise_ledger_error": float(np.max(np.abs(ledger))),
            "mask_agreement": bool(mismatch.size == 0),
            "mask_mismatch_indices": mismatch.tolist(),
            "unsupported_topologies": unsupported,
            "hard_gate": hard,
            "uncertainty_semantics": "heuristic_training_residual_scale/not_calibrated_physical_uncertainty"}


def spatial_holdout(*, angles: np.ndarray, aggregates: np.ndarray,
                    candidate: str, jitter: float, windows: dict[str, np.ndarray]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, holdout in windows.items():
        train_mask = np.ones(len(angles), dtype=bool); train_mask[holdout] = False
        train = np.flatnonzero(train_mask)
        if len(holdout) < 4 or len(train) < 8:
            result[name] = {"status": "insufficient_support", "n": int(len(holdout))}
            continue
        model = AggregateModel(candidate, jitter=jitter, gp_starts=8).fit(
            angles[train], aggregates[train, :3],
        )
        prediction = model.predict(angles[holdout])
        result[name] = {"status": "measured", "n": int(len(holdout)),
                        "heldout_indices": holdout.tolist(),
                        "metrics": {target: _metrics(aggregates[holdout, i], prediction[:, i])
                                    for i, target in enumerate(PRIMARY_TARGETS)}}
    hard = all(values.get("status") == "measured" and
               all(values["metrics"][target]["p95_abs"] <= 0.02
                   for target in PRIMARY_TARGETS) for values in result.values())
    return {"windows": result, "hard_gate": bool(hard), "candidate": candidate}


def _candidate_score(result: dict[str, Any]) -> float:
    metrics = result["metrics"]
    score = max(max(item["nrmse"] / 0.01, item["p95_abs"] / 0.01,
                    item["max_abs"] / 0.03) for item in metrics.values())
    if result.get("spatial_holdout"):
        for item in result["spatial_holdout"]["windows"].values():
            if item.get("status") == "measured":
                score = max(score, max(item["metrics"][target]["p95_abs"] / 0.02
                                       for target in PRIMARY_TARGETS))
    return float(score)


def _result_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items()
            if key not in {"oof_prediction", "oof_std", "power_oof_records"}}


def run_training_cv(*, dataset_dir: Path, output_dir: Path,
                    spatial_windows_path: Path,
                    mask_coverage_path: Path | None = None) -> dict[str, Any]:
    manifest = verify_immutable_package(dataset_dir)
    data = load_training_dataset(dataset_dir)
    angles = np.asarray(data["angles.npy"], dtype=np.float64)
    aggregates = np.asarray(data["aggregates.npy"], dtype=np.float64)
    powers = np.asarray(data["order_powers.npy"], dtype=np.float64)
    mask = np.asarray(data["power_carrying_mask.npy"], dtype=bool)
    if len(angles) not in (96, 112):
        raise ValueError("Task004 CV must use train96 or train112 only")
    windows = _load_windows(spatial_windows_path, angles,
                            manifest["training_tuple_sha256"])
    split = folds(angle_features(angles, "F1"), n_splits=5, seed=FOLD_SEED)
    split_identity = fold_identity(angle_features(angles, "F1"), split, seed=FOLD_SEED)
    candidate_results: list[dict[str, Any]] = []
    baseline_results: list[dict[str, Any]] = []
    production_results: list[dict[str, Any]] = []
    for name, jitter in BASELINE_CANDIDATES + PRODUCTION_CANDIDATES:
        prediction = np.full((len(angles), 3), np.nan)
        std = np.full_like(prediction, np.nan)
        fold_rows = []
        for fold, (train, test) in enumerate(split):
            fold_prediction, fold_std, metadata = _fit_fold(
                name, jitter, angles[train], aggregates[train], angles[test],
            )
            prediction[test] = fold_prediction; std[test] = fold_std
            fold_rows.append({"fold": fold, "train_indices": train.tolist(),
                              "test_indices": test.tolist(), "metadata": metadata})
        metrics = {target: _metrics(aggregates[:, i], prediction[:, i])
                   for i, target in enumerate(PRIMARY_TARGETS)}
        regions = _region_metrics(angles, aggregates[:, :3], prediction)
        calibration = _calibrate_cross_fitted(
            aggregates[:, :3], prediction, std, split, angles,
        )
        result = {"candidate": name, "jitter": jitter, "family": "production_gp" if name.startswith("gp:") else "diagnostic_baseline",
                  "metrics": metrics, "region_breakdown": regions,
                  "folds": fold_rows, "composition_exact": bool(
                      np.max(np.abs(np.sum(prediction, axis=1) - 1.0)) <= 1.0e-12),
                  "aggregate_gate": _aggregate_gate(metrics, regions),
                  "uncertainty": calibration,
                  "uncertainty_gate": bool(calibration.get("gate", False)) if name.startswith("gp:") else False}
        result["oof_prediction"] = prediction; result["oof_std"] = std
        if name.startswith("gp:"):
            result["spatial_holdout"] = spatial_holdout(
                angles=angles, aggregates=aggregates, candidate=name,
                jitter=jitter, windows=windows,
            )
            power = _power_oof(
                angles=angles, aggregates=aggregates, powers=powers, mask=mask,
                split=split, aggregate_candidate=name, aggregate_jitter=jitter,
                aggregate_prediction=prediction, aggregate_std=std,
                feature=name.split(":", 1)[1],
            )
            result["power"] = power
            result["power_oof_records"] = power["records"]
            result["power_gate"] = bool(power["hard_gate"])
            result["spatial_gate"] = bool(result["spatial_holdout"]["hard_gate"])
            result["candidate_eligible"] = bool(
                result["aggregate_gate"] and result["spatial_gate"] and
                result["uncertainty_gate"] and result["power_gate"] and
                result["composition_exact"])
            production_results.append(result)
        else:
            result["candidate_eligible"] = False
            baseline_results.append(result)
        result["selection_score"] = _candidate_score(result)
        candidate_results.append(result)
    eligible = [item for item in production_results if item["candidate_eligible"]]
    ranked = sorted(eligible or production_results,
                    key=lambda item: (item["selection_score"], item["candidate"], item["jitter"]))
    if not ranked:
        raise RuntimeError("Task004 produced no production candidate")
    selected = ranked[0]
    selected_prediction = selected["oof_prediction"]
    selected_std = selected["oof_std"]
    feature = selected["candidate"].split(":", 1)[1]
    nearest = np.full(len(angles), np.nan)
    fold_for_index: dict[int, int] = {}
    for fold, (train, test) in enumerate(split):
        nearest[test] = _nearest_distance(angles[test], angles[train], feature)
        fold_for_index.update({int(index): fold for index in test})
    labels = region_labels(angles); masks = region_masks(angles)
    cutoff_order, signed_margin = cutoff_identity(angles)
    window_membership = {name: set(int(i) for i in indices) for name, indices in windows.items()}
    oof_records = []
    for index in range(len(angles)):
        for target_index, target in enumerate(PRIMARY_TARGETS):
            oof_records.append({
                "sample_index": index, "target": target,
                "truth": float(aggregates[index, target_index]),
                "prediction": float(selected_prediction[index, target_index]),
                "std": float(selected_std[index, target_index]) if np.isfinite(selected_std[index, target_index]) else None,
                "error": float(selected_prediction[index, target_index] - aggregates[index, target_index]),
                "fold": fold_for_index[index], "region": labels[index],
                "regions": [name for name, region in masks.items() if bool(region[index])],
                "spatial_windows": [name for name, values in window_membership.items() if index in values],
                "cutoff_order": int(cutoff_order[index]),
                "signed_cutoff_margin": float(signed_margin[index]),
                "nearest_actual_fold_training_distance": float(nearest[index]),
            })
    if np.any(nearest <= 0.0):
        raise RuntimeError("Task004 nearest actual fold-training distance is zero")
    baseline_best = min(baseline_results, key=lambda item: item["selection_score"])
    active_eligibility = False
    if not eligible:
        correlations = []
        for i in range(3):
            if np.all(np.isfinite(selected_std[:, i])):
                correlations.append(float(np.corrcoef(
                    np.abs(selected_prediction[:, i] - aggregates[:, i]),
                    selected_std[:, i],
                )[0, 1]))
        coverage_ok = True
        if mask_coverage_path is not None and mask_coverage_path.is_file():
            coverage = json.loads(mask_coverage_path.read_text())
            coverage_ok = (not coverage.get("validation_unseen_signatures") and
                           all(item.get("all_test_supported") for item in coverage.get("fold_support", [])))
        active_eligibility = bool(
            selected["selection_score"] < baseline_best["selection_score"] and
            sum(value > 0.0 for value in correlations) >= 2 and coverage_ok
        )
        # Contract/data failures must never qualify for active learning.
        active_eligibility = bool(active_eligibility and manifest.get("source_dirty") is False
                                  and selected["power"].get("mask_agreement")
                                  and not selected["power"].get("unsupported_topologies"))
    dataset_hashes = json.loads((dataset_dir / "file_hashes.json").read_text())
    report = {
        "schema_version": "task004.training-cv.v3",
        "dataset_id": manifest["dataset_id"],
        "forward_solver_sha": manifest["forward_solver_sha"],
        "surrogate_training_code_sha": manifest.get("surrogate_dataset_builder_sha"),
        "dataset_file_hashes": dataset_hashes,
        "training_count": len(angles), "feature_candidates": ["F1", "F2", "F3"],
        "production_candidates": [f"{name}:{jitter:g}" for name, jitter in PRODUCTION_CANDIDATES],
        "baseline_candidates": [name for name, _ in BASELINE_CANDIDATES],
        "baseline_results": [_result_summary(item) for item in baseline_results],
        "candidate_results": [_result_summary(item) for item in candidate_results],
        "selected_candidate": selected["candidate"], "selected_feature": feature,
        "selected_jitter": selected["jitter"],
        "selected_result": _result_summary(selected),
        "power": {key: value for key, value in selected["power"].items()
                  if key not in {"records"}},
        "power_oof_records": selected["power_oof_records"],
        "spatial_holdout": selected["spatial_holdout"],
        "fold_identity": split_identity,
        "oof_records": oof_records,
        "validation_target_accessed": False,
        "training_gate": bool(eligible and selected["candidate_eligible"]),
        "aggregate_gate": bool(selected["aggregate_gate"]),
        "spatial_holdout_gate": bool(selected["spatial_gate"]),
        "uncertainty_gate": bool(selected["uncertainty_gate"]),
        "power_gate": bool(selected["power_gate"]),
        "active_learning_eligibility": active_eligibility,
        "allowed_jitters": list(ALLOWED_JITTERS),
        "optimizer_initial_count": 8,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report.pop("oof_records")
    (output_dir / "training_cv.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    (output_dir / "training_cv_oof.json").write_text(
        json.dumps({"schema_version": "task004.training-cv-oof.v3",
                    "records": oof_records}, indent=2, sort_keys=True) + "\n"
    )
    return report


def fit_final_model(*, dataset_dir: Path, report: dict[str, Any], output_dir: Path,
                    expected_forward_solver_sha: str = FORWARD_SOLVER_SHA) -> dict[str, Any]:
    """Fit the locked training model; every qualification gate is fail-closed."""
    if report.get("validation_target_accessed") is not False:
        raise RuntimeError("Task004 model lock refuses validation-target access")
    required = ("training_gate", "aggregate_gate", "spatial_holdout_gate",
                "uncertainty_gate", "power_gate")
    if not all(bool(report.get(key)) for key in required):
        raise RuntimeError("Task004 model lock requires all training gates")
    manifest = verify_immutable_package(dataset_dir)
    if manifest.get("forward_solver_sha") != expected_forward_solver_sha:
        raise RuntimeError("Task004 model lock forward SHA mismatch")
    if report.get("forward_solver_sha") != expected_forward_solver_sha:
        raise RuntimeError("Task004 report forward SHA mismatch")
    data = load_training_dataset(dataset_dir)
    angles = np.asarray(data["angles.npy"], dtype=np.float64)
    selected = AggregateModel(report["selected_candidate"],
                              jitter=float(report["selected_jitter"]), gp_starts=8).fit(
                                  angles, data["aggregates.npy"][:, :3])
    power_model = MaskedFractionPowerModel(feature=report["selected_feature"]).fit(
        angles, data["order_powers.npy"], analytic_power_carrying_mask(angles),
    )
    factors = report["selected_result"]["uncertainty"]["final_factors"]
    package = {
        "aggregate_model": selected, "power_model": power_model,
        "training_angles": angles, "training_count": len(angles),
        "selected_candidate": report["selected_candidate"],
        "selected_feature": report["selected_feature"],
        "dataset_id": report["dataset_id"],
        "forward_solver_sha": expected_forward_solver_sha,
        "surrogate_training_code_sha": manifest.get("surrogate_dataset_builder_sha"),
        "calibration_factors": factors,
        "model_metadata": selected.metadata(),
        "power_model_metadata": power_model.metadata(),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "angle_model.pkl").open("wb") as stream:
        pickle.dump(package, stream, protocol=4)
    lock = {
        "schema_version": "task004.angle-model-selection-lock.v2",
        "dataset_id": report["dataset_id"],
        "forward_solver_sha": expected_forward_solver_sha,
        "surrogate_training_code_sha": manifest.get("surrogate_dataset_builder_sha"),
        "dataset_file_hashes": json.loads((dataset_dir / "file_hashes.json").read_text()),
        "training_tuple_sha256": manifest.get("training_tuple_sha256"),
        "training_design_id": manifest.get("training_design_id"),
        "selected_candidate": report["selected_candidate"],
        "feature": report["selected_feature"], "jitter": report["selected_jitter"],
        "gp_optimizer_initial_count": 8, "allowed_jitters": list(ALLOWED_JITTERS),
        "fold_seed": FOLD_SEED,
        "uncertainty_calibration_factors": factors,
        "power_model": power_model.metadata(),
        "training_gate": True, "aggregate_gate": True,
        "spatial_holdout_gate": True, "uncertainty_gate": True, "power_gate": True,
        "validation_target_accessed": False,
        "blind_validation_status": "not_run",
    }
    (output_dir / "ANGLE_MODEL_SELECTION_LOCK.json").write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n"
    )
    return package
