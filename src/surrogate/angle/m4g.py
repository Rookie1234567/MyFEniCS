"""Task004 Required M4G: train112 local-model closure.

This module is deliberately training-only.  It freezes a fresh 112-row outer
fold split, evaluates the finite local candidates approved by Review V5, and
compares two deterministic latent ensembles.  No validation response or FEM
runner is imported here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize

from ..folds import FOLD_SEED, fold_identity, folds
from .dataset import load_training_dataset, verify_immutable_package
from .m4e import (
    TARGETS,
    _aggregate,
    _crossfit_calibration,
    _evaluate_candidate,
    _hash as m4e_hash,
    _latent,
    _load_windows,
    _make_candidate,
    _metrics,
    _summary,
)
from .models import (
    analytic_power_carrying_mask,
    angle_features,
    cutoff_identity,
    region_labels,
    region_masks,
)


LOCAL_SPECS: tuple[dict[str, Any], ...] = (
    {"candidate": "L1_local_rbf_k24_s1e-08", "family": "local_rbf",
     "neighbors": 24, "smoothing": 1.0e-8, "feature": "F1"},
    {"candidate": "L2_local_matern_k24", "family": "local_matern",
     "neighbors": 24, "jitter": 1.0e-8, "feature": "F1"},
    {"candidate": "L2_local_matern_k32", "family": "local_matern",
     "neighbors": 32, "jitter": 1.0e-8, "feature": "F1"},
    {"candidate": "L4_trend_local_residual_k24", "family": "trend_local_residual",
     "neighbors": 24, "smoothing": 1.0e-8, "feature": "F1"},
)
BASE_NAMES = tuple(spec["candidate"] for spec in LOCAL_SPECS)
ENSEMBLE_NAMES = ("E1_latent_median_ensemble", "E2_cross_fitted_nonnegative_stack")


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def _tuple_hash(rows: list[list[float]]) -> str:
    return _hash(rows)


def _to_latent(aggregates: np.ndarray) -> np.ndarray:
    values = np.asarray(aggregates, dtype=np.float64)
    eps = 1.0e-8
    return np.column_stack((np.log((values[:, 0] + eps) / (values[:, 2] + eps)),
                            np.log((values[:, 1] + eps) / (values[:, 2] + eps))))


def _old_new(index: int) -> str:
    return "old96" if int(index) < 96 else "new16"


def _signature(row: np.ndarray) -> str:
    return ";".join(str(int(value)) for value in np.flatnonzero(row))


def _summary_metrics(truth: np.ndarray, prediction: np.ndarray,
                     indices: np.ndarray) -> dict[str, dict[str, Any]]:
    return {target: _metrics(truth[indices, i], prediction[indices, i])
            for i, target in enumerate(TARGETS)}


def _aggregate_gate(metrics: dict[str, dict[str, Any]]) -> bool:
    return bool(all(item["nrmse"] <= 0.01 and item["p95_abs"] <= 0.01 and
                    item["max_abs"] <= 0.03 for item in metrics.values()))


def _window_gate(window_metrics: dict[str, Any]) -> bool:
    return bool(all(all(value["metrics"][target]["p95_abs"] <= 0.02
                         for target in TARGETS)
                    for value in window_metrics.values()))


def _fold_distance(query: np.ndarray, train: np.ndarray) -> np.ndarray:
    q = angle_features(query, "F1")
    t = angle_features(train, "F1")
    return np.min(np.linalg.norm(q[:, None, :] - t[None, :, :], axis=2), axis=1)


def freeze_train112_reference_folds(*, dataset_dir: Path, output: Path,
                                    implementation_sha: str) -> dict[str, Any]:
    """Freeze folds and response-blind support metadata before model fitting."""
    manifest = verify_immutable_package(dataset_dir,
                                        expected_dataset_id="task004_angle_nominal_p5_ny4_train112_v1")
    data = load_training_dataset(dataset_dir)
    angles = np.asarray(data["angles.npy"], dtype=np.float64)
    inputs = np.asarray(data["inputs.npy"], dtype=np.float64)
    masks = np.asarray(data["power_carrying_mask.npy"], dtype=bool)
    split = folds(angle_features(angles, "F1"), n_splits=5, seed=FOLD_SEED)
    rows = []
    for fold, (train, test) in enumerate(split):
        distance = _fold_distance(angles[test], angles[train])
        test_signatures = [_signature(masks[index]) for index in test]
        train_signatures = {_signature(masks[index]) for index in train}
        support_counts: dict[str, dict[str, Any]] = {}
        for signature in sorted(set(test_signatures)):
            count = test_signatures.count(signature)
            support_counts[signature] = {
                "test_count": count,
                "train_count": int(sum(_signature(masks[index]) == signature for index in train)),
                "supported_in_outer_train": signature in train_signatures,
            }
        fold_row = {
            "fold": fold,
            "train_indices": train.tolist(), "test_indices": test.tolist(),
            "train_tuples": inputs[train].round(12).tolist(),
            "test_tuples": inputs[test].round(12).tolist(),
            "test_old96_count": int(np.sum(test < 96)),
            "test_new16_count": int(np.sum(test >= 96)),
            "mask_signature_support": support_counts,
            "nearest_training_distance": {
                "min": float(np.min(distance)), "p50": float(np.percentile(distance, 50)),
                "p95": float(np.percentile(distance, 95)), "max": float(np.max(distance)),
                "values": distance.tolist(),
            },
        }
        fold_row["fold_sha256"] = _hash({
            "fold": fold, "train_indices": train.tolist(), "test_indices": test.tolist(),
            "test_tuples": inputs[test].round(12).tolist(),
        })
        rows.append(fold_row)
    payload = {
        "schema_version": "task004.train112-local-reference-folds.v1",
        "dataset_id": manifest["dataset_id"],
        "training_count": 112,
        "training_tuple_sha256": manifest["training_tuple_sha256"],
        "surrogate_training_code_sha": implementation_sha,
        "fold_seed": FOLD_SEED, "n_splits": 5,
        "fold_identity": fold_identity(angle_features(angles, "F1"), split, seed=FOLD_SEED),
        "folds": rows,
        "test_coverage": {
            "counts": np.bincount(np.concatenate([row["test_indices"] for row in rows]), minlength=112).tolist(),
            "each_index_once": True,
            "old96_count": 96, "new16_count": 16,
        },
        "validation_target_accessed": False,
    }
    if output.is_file():
        old = json.loads(output.read_text())
        old_structure = dict(old)
        old_structure.pop("surrogate_training_code_sha", None)
        new_structure = dict(payload)
        new_structure.pop("surrogate_training_code_sha", None)
        if old_structure != new_structure:
            raise ValueError("frozen train112 folds already exist with a different identity")
        # The fold rows are the immutable authority.  A later implementation
        # fix may rebind only the provenance SHA; it may not alter any split or
        # support statistic.
        if old.get("surrogate_training_code_sha") != implementation_sha:
            old["surrogate_training_code_sha"] = implementation_sha
            output.write_text(json.dumps(old, indent=2, sort_keys=True) + "\n")
        return old
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def _subgroup_metrics(truth: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    return {
        "old96": _summary_metrics(truth, prediction, np.arange(96, dtype=np.int64)),
        "new16": _summary_metrics(truth, prediction, np.arange(96, 112, dtype=np.int64)),
    }


def _base_result(spec: dict[str, Any], angles: np.ndarray, aggregates: np.ndarray,
                 split: list[tuple[np.ndarray, np.ndarray]],
                 windows: dict[str, np.ndarray]) -> dict[str, Any]:
    return _evaluate_candidate(spec, angles, aggregates, split, windows)


def _simplex_weights(features: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    values = np.asarray(features, dtype=np.float64)
    truth = np.asarray(target, dtype=np.float64)
    count = values.shape[1]

    def objective(weights: np.ndarray) -> float:
        residual = values @ weights - truth
        return float(np.mean(residual * residual))

    result = minimize(objective, np.full(count, 1.0 / count), method="SLSQP",
                      bounds=[(0.0, 1.0)] * count,
                      constraints={"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)},
                      options={"ftol": 1.0e-12, "maxiter": 500, "disp": False})
    weights = np.asarray(result.x if result.success else np.full(count, 1.0 / count), dtype=np.float64)
    weights = np.maximum(weights, 0.0); weights /= np.sum(weights)
    return weights, {"success": bool(result.success), "status": int(result.status),
                     "message": str(result.message), "objective": objective(weights),
                     "weights": weights.tolist()}


def _inner_oof_latent(spec: dict[str, Any], angles: np.ndarray, aggregates: np.ndarray,
                      seed: int) -> tuple[np.ndarray, dict[str, Any]]:
    inner_split = folds(angle_features(angles, "F1"), n_splits=3, seed=seed)
    prediction = np.full((len(angles), 2), np.nan, dtype=np.float64)
    for train, test in inner_split:
        model = _make_candidate(spec).fit(angles[train], aggregates[train])
        mean, _ = model.predict(angles[test])
        prediction[test] = _to_latent(mean)
    return prediction, {"fold_identity": fold_identity(angle_features(angles, "F1"), inner_split, seed=seed)}


def _fit_stack_weights(train_indices: np.ndarray, angles: np.ndarray,
                       aggregates: np.ndarray, specs: tuple[dict[str, Any], ...],
                       seed: int) -> tuple[np.ndarray, dict[str, Any]]:
    train_indices = np.asarray(train_indices, dtype=np.int64)
    local_angles = angles[train_indices]
    local_aggregates = aggregates[train_indices]
    inner_predictions = []
    inner_meta = []
    for spec in specs[:3]:
        prediction, meta = _inner_oof_latent(spec, local_angles, local_aggregates, seed)
        inner_predictions.append(prediction); inner_meta.append(meta)
    stacked = np.stack(inner_predictions, axis=2)
    truth = _latent(local_aggregates)
    weights = np.empty((2, 3), dtype=np.float64)
    reports = []
    for target in range(2):
        weights[target], report = _simplex_weights(stacked[:, target, :], truth[:, target])
        reports.append(report)
    return weights, {"inner": inner_meta, "targets": reports, "train_indices": train_indices.tolist()}


def _ensemble_window_metrics(mode: str, angles: np.ndarray, aggregates: np.ndarray,
                             holdout: np.ndarray, specs: tuple[dict[str, Any], ...],
                             global_split: list[tuple[np.ndarray, np.ndarray]]) -> dict[str, Any]:
    train = np.asarray([i for i in range(len(angles)) if i not in set(holdout)], dtype=np.int64)
    predictions = []
    for spec in specs[:3]:
        model = _make_candidate(spec).fit(angles[train], aggregates[train])
        predictions.append(_to_latent(model.predict(angles[holdout])[0]))
    stacked = np.stack(predictions, axis=2)
    if mode == "median":
        latent = np.median(stacked, axis=2)
    else:
        weights, _ = _fit_stack_weights(train, angles, aggregates, specs, FOLD_SEED + 901)
        latent = np.stack([stacked[:, target, :] @ weights[target] for target in range(2)], axis=1)
    prediction = _aggregate(latent)
    return {"indices": holdout.tolist(),
            "metrics": _summary_metrics(aggregates[:, :3], prediction,
                                          np.arange(len(holdout), dtype=np.int64)) if False else
                       {target: _metrics(aggregates[holdout, i], prediction[:, i])
                        for i, target in enumerate(TARGETS)}}


def _build_ensembles(angles: np.ndarray, aggregates: np.ndarray,
                     split: list[tuple[np.ndarray, np.ndarray]],
                     base_results: dict[str, dict[str, Any]],
                     windows: dict[str, np.ndarray]) -> dict[str, dict[str, Any]]:
    base_predictions = np.stack([base_results[name]["oof_prediction"] for name in BASE_NAMES[:3]], axis=2)
    base_stds = np.stack([base_results[name]["oof_std"] for name in BASE_NAMES[:3]], axis=2)
    median_latent = np.median(np.stack([_to_latent(base_results[name]["oof_prediction"])
                                        for name in BASE_NAMES[:3]], axis=2), axis=2)
    median_prediction = _aggregate(median_latent)
    median_dispersion = np.std(base_predictions, axis=2)
    median_native = np.nanmedian(base_stds, axis=2)
    median_std = np.maximum(np.nan_to_num(median_native, nan=0.0), median_dispersion)
    median_std = np.maximum(median_std, 1.0e-8)

    stack_prediction = np.full((len(angles), 3), np.nan)
    stack_std = np.full_like(stack_prediction, np.nan)
    stack_weights: list[dict[str, Any]] = []
    for fold, (train, test) in enumerate(split):
        weights, weight_meta = _fit_stack_weights(train, angles, aggregates,
                                                   LOCAL_SPECS, FOLD_SEED + 701 + fold)
        stack_weights.append({"fold": fold, "weights": weights.tolist(), "provenance": weight_meta})
        latent_models = np.stack([_to_latent(base_results[name]["oof_prediction"][test])
                                  for name in BASE_NAMES[:3]], axis=2)
        latent = np.stack([latent_models[:, target, :] @ weights[target]
                           for target in range(2)], axis=1)
        stack_prediction[test] = _aggregate(latent)
        # The stack weights are learned in the two latent coordinates, while
        # the reported uncertainty is in physical R/T/A coordinates.  Use a
        # conservative physical-space ensemble spread here; cross-fitted
        # calibration below supplies the target-wise correction.
        spread = np.std(base_predictions[test], axis=2)
        weighted_std = np.sqrt(np.mean(np.nan_to_num(base_stds[test], nan=0.0) ** 2,
                                       axis=2))
        stack_std[test] = np.maximum(np.maximum(spread, weighted_std), 1.0e-8)

    ensembles: dict[str, dict[str, Any]] = {}
    for name, prediction, raw_std, mode in (
        (ENSEMBLE_NAMES[0], median_prediction, median_std, "median"),
        (ENSEMBLE_NAMES[1], stack_prediction, stack_std, "stack"),
    ):
        metrics = _summary_metrics(aggregates[:, :3], prediction, np.arange(len(angles)))
        regions = {region: _summary_metrics(aggregates[:, :3], prediction, np.flatnonzero(mask))
                   if np.any(mask) else {} for region, mask in region_masks(angles).items()}
        uncertainty = _crossfit_calibration(aggregates[:, :3], prediction, raw_std, split, angles)
        supported = {window_name: _ensemble_window_metrics(
            "median" if mode == "median" else "stack", angles, aggregates,
            holdout, LOCAL_SPECS, split
        ) for window_name, holdout in windows.items()}
        aggregate_gate = _aggregate_gate(metrics)
        supported_gate = _window_gate(supported)
        result = {
            "candidate": name,
            "family": "ensemble",
            "ensemble_rule": mode,
            "base_candidates": list(BASE_NAMES[:3]),
            "metrics": metrics,
            "region_metrics": regions,
            "supported_window_metrics": supported,
            "aggregate_gate": aggregate_gate,
            "supported_window_gate": supported_gate,
            "composition_exact": bool(np.max(np.abs(np.sum(prediction, axis=1) - 1.0)) <= 1.0e-12),
            "uncertainty": uncertainty,
            "aggregate_qualified": bool(aggregate_gate and supported_gate and
                                         result_get(uncertainty, "gate") and
                                         np.max(np.abs(np.sum(prediction, axis=1) - 1.0)) <= 1.0e-12),
            "oof_prediction": prediction,
            "oof_std": raw_std,
            "stack_weights": stack_weights if mode == "stack" else None,
            "subgroup_metrics": _subgroup_metrics(aggregates[:, :3], prediction),
        }
        result["selection_score"] = _selection_score(metrics, supported)
        ensembles[name] = result
    return ensembles


def result_get(value: dict[str, Any], key: str) -> Any:
    return value.get(key)


def _selection_score(metrics: dict[str, Any], supported: dict[str, Any]) -> float:
    score = max(max(item["nrmse"] / 0.01, item["p95_abs"] / 0.01,
                    item["max_abs"] / 0.03) for item in metrics.values())
    for item in supported.values():
        score = max(score, max(item["metrics"][target]["p95_abs"] / 0.02 for target in TARGETS))
    return float(score)


def _base_point_diagnostic(result: dict[str, Any], index: int, angles: np.ndarray) -> dict[str, Any]:
    point = result["point_diagnostics"][int(index)]
    latent = point.get("latent_diagnostics", [])
    first = latent[0] if latent else {}
    neighbor_indices = first.get("neighbor_indices", [])
    return {
        "fold": int(point["fold"]),
        "inner_radius": point.get("inner_radius"),
        "nearest_fold_training_distance": first.get("nearest_distance"),
        "neighbor_indices": neighbor_indices,
        "neighbor_tuples": angles[np.asarray(neighbor_indices, dtype=np.int64)].round(12).tolist()
        if neighbor_indices else [],
        "latent_diagnostics": latent,
        "unsupported": point.get("unsupported", []),
    }


def _make_oof_records(angles: np.ndarray, aggregates: np.ndarray, masks: np.ndarray,
                      split: list[tuple[np.ndarray, np.ndarray]],
                      results: dict[str, dict[str, Any]], plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    fold_for_index = {}
    for fold, (_, test) in enumerate(split):
        fold_for_index.update({int(index): fold for index in test})
    cutoff_order, signed_margin = cutoff_identity(angles)
    regions = region_masks(angles)
    plan_by_angle = {tuple(np.asarray(point["angle"], dtype=np.float64).round(12)): point
                     for point in plan.get("points", [])}
    records: dict[str, list[dict[str, Any]]] = {}
    for name, result in results.items():
        prediction = result["oof_prediction"]
        std = result["oof_std"]
        rows = []
        for index in range(len(angles)):
            key = tuple(angles[index].round(12))
            plan_row = plan_by_angle.get(key)
            row = {
                "sample_index": index,
                "angle": angles[index].round(12).tolist(),
                "identity": _old_new(index),
                "fold": int(fold_for_index[index]),
                "truth": aggregates[index, :3].tolist(),
                "prediction": prediction[index].tolist(),
                "std": std[index].tolist(),
                "error": (prediction[index] - aggregates[index, :3]).tolist(),
                "absolute_error": np.abs(prediction[index] - aggregates[index, :3]).tolist(),
                "mask_signature": _signature(masks[index]),
                "cutoff_order": int(cutoff_order[index]),
                "signed_cutoff_margin": float(signed_margin[index]),
                "region_labels": [region for region, values in regions.items() if bool(values[index])],
                "round1_acquisition": plan_row if plan_row else None,
            }
            if name in BASE_NAMES:
                row["diagnostic"] = _base_point_diagnostic(result, index, angles)
            rows.append(row)
        records[name] = rows
    return records


def _classification(row: dict[str, Any], thresholds: dict[str, float]) -> tuple[str, dict[str, Any]]:
    distance = float(row["nearest_training_distance"])
    disagreement = float(row["model_disagreement"])
    margin = abs(float(row["signed_cutoff_margin"]))
    boundary = bool(row["angle"][0] in (0.5, 10.0) or row["angle"][1] in (0.0, 90.0))
    if distance >= thresholds["distance_q75"] and disagreement <= thresholds["disagreement_q75"]:
        return "coverage_hole", {"distance_high": True, "disagreement_high": False}
    if margin <= 0.02 and disagreement >= thresholds["disagreement_q50"]:
        return "cutoff_high_curvature", {"cutoff_near": True, "disagreement_high": True}
    if boundary and distance >= thresholds["distance_q50"]:
        return "boundary_one_sided", {"boundary": True, "distance_high": True}
    if disagreement >= thresholds["disagreement_q75"]:
        return "model_instability", {"disagreement_high": True}
    return "unexplained", {"distance_high": False, "disagreement_high": False}


def build_outlier_audit(*, angles: np.ndarray, aggregates: np.ndarray, masks: np.ndarray,
                        base_results: dict[str, dict[str, Any]],
                        all_results: dict[str, dict[str, Any]],
                        oof_records: dict[str, list[dict[str, Any]]],
                        plan: dict[str, Any], output_json: Path, output_md: Path,
                        implementation_sha: str) -> dict[str, Any]:
    reference_name = min(all_results, key=lambda name: all_results[name]["selection_score"])
    reference = all_results[reference_name]
    reference_error = np.abs(reference["oof_prediction"] - aggregates[:, :3])
    base_prediction = np.stack([base_results[name]["oof_prediction"] for name in BASE_NAMES[:3]], axis=2)
    disagreement = np.max(base_prediction, axis=2) - np.min(base_prediction, axis=2)
    nearest = np.asarray([_base_point_diagnostic(base_results[BASE_NAMES[1]], i, angles)
                          ["nearest_fold_training_distance"] for i in range(len(angles))], dtype=float)
    finite_nearest = nearest[np.isfinite(nearest)]
    thresholds = {
        "distance_q50": float(np.percentile(finite_nearest, 50)),
        "distance_q75": float(np.percentile(finite_nearest, 75)),
        "disagreement_q50": float(np.percentile(disagreement, 50)),
        "disagreement_q75": float(np.percentile(disagreement, 75)),
    }
    cutoff_order, signed_margin = cutoff_identity(angles)
    plan_by_angle = {tuple(np.asarray(point["angle"]).round(12)): point for point in plan.get("points", [])}
    targets: dict[str, list[dict[str, Any]]] = {}
    for target_index, target in enumerate(TARGETS):
        indices = np.argsort(reference_error[:, target_index], kind="mergesort")[-10:][::-1]
        rows = []
        for index in indices:
            candidate_values = {}
            for name, result in all_results.items():
                candidate_values[name] = {
                    "prediction": float(result["oof_prediction"][index, target_index]),
                    "std": float(result["oof_std"][index, target_index]),
                    "error": float(result["oof_prediction"][index, target_index] - aggregates[index, target_index]),
                    "absolute_error": float(abs(result["oof_prediction"][index, target_index] - aggregates[index, target_index])),
                }
            diagnostic = _base_point_diagnostic(base_results[BASE_NAMES[1]], int(index), angles)
            row = {
                "sample_index": int(index), "angle": angles[index].round(12).tolist(),
                "identity": _old_new(int(index)), "fold": diagnostic["fold"],
                "target": target, "truth": float(aggregates[index, target_index]),
                "reference_candidate": reference_name,
                "reference_absolute_error": float(reference_error[index, target_index]),
                "candidates": candidate_values,
                "nearest_fold_training_distance": float(nearest[index]),
                "nearest_training_tuples": diagnostic["neighbor_tuples"],
                "mask_signature": _signature(masks[index]),
                "cutoff_order": int(cutoff_order[index]),
                "signed_cutoff_margin": float(signed_margin[index]),
                "region_labels": [name for name, values in region_masks(angles).items() if bool(values[index])],
                "model_disagreement": float(disagreement[index, target_index]),
                "round1_acquisition": plan_by_angle.get(tuple(angles[index].round(12))),
            }
            classification, evidence = _classification(row, thresholds)
            row["classification"] = classification
            row["classification_evidence"] = evidence
            rows.append(row)
        targets[target] = rows
    payload = {
        "schema_version": "task004.post-active-outlier-audit.v1",
        "dataset_id": "task004_angle_nominal_p5_ny4_train112_v1",
        "surrogate_training_code_sha": implementation_sha,
        "reference_candidate": reference_name,
        "candidate_set": list(all_results),
        "classification_contract": {
            "coverage_hole": "distance >= q75 and disagreement <= q75",
            "cutoff_high_curvature": "abs(signed cutoff margin) <= 0.02 and disagreement >= q50",
            "boundary_one_sided": "domain boundary and distance >= q50",
            "model_instability": "disagreement >= q75",
            "unexplained": "none of the preceding evidence rules",
        },
        "thresholds": thresholds,
        "targets": targets,
        "validation_target_accessed": False,
    }
    output_json.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
    lines = ["# POST_ACTIVE_OUTLIER_AUDIT", "",
             f"Reference candidate: `{reference_name}`.  The audit is training-only and lists the ten highest absolute-error points per target.", "",
             "| target | rank | index | identity | angle | abs error | classification | distance | disagreement |", "|---|---:|---:|---|---|---:|---|---:|---:|"]
    for target, rows in targets.items():
        for rank, row in enumerate(rows, 1):
            lines.append(f"| {target} | {rank} | {row['sample_index']} | {row['identity']} | {row['angle']} | {row['reference_absolute_error']:.8g} | {row['classification']} | {row['nearest_fold_training_distance']:.6g} | {row['model_disagreement']:.6g} |")
    lines += ["", "The JSON contains every candidate prediction/std/error, nearest training tuples, cutoff/mask/region identity, and the immutable Round1 acquisition metadata when a point was selected."]
    output_md.write_text("\n".join(lines) + "\n")
    return payload


def build_safe_domain_candidate(*, dataset_dir: Path, angles: np.ndarray,
                                masks: np.ndarray, base_results: dict[str, dict[str, Any]],
                                candidate_pool: Path, output: Path,
                                implementation_sha: str) -> dict[str, Any]:
    pool = json.loads(candidate_pool.read_text())
    pool_angles = np.asarray([[float(row["grazing_deg"]), float(row["azimuth_deg"])]
                              for row in pool["points"]], dtype=np.float64)
    train_mask_signatures = {_signature(row) for row in masks}
    pool_mask = analytic_power_carrying_mask(pool_angles)
    pool_signatures = np.asarray([_signature(row) for row in pool_mask], dtype=object)
    distance = _fold_distance(pool_angles, angles)
    oof_distance = np.asarray([_base_point_diagnostic(base_results[BASE_NAMES[1]], i, angles)
                               ["nearest_fold_training_distance"] for i in range(len(angles))], dtype=float)
    threshold = float(np.percentile(oof_distance, 95))
    safe = (distance <= threshold) & np.asarray([value in train_mask_signatures for value in pool_signatures])
    payload = {
        "schema_version": "task004.aggregate-safe-domain-candidate.v1",
        "dataset_id": "task004_angle_nominal_p5_ny4_train112_v1",
        "surrogate_training_code_sha": implementation_sha,
        "response_blind_candidate_pool": True,
        "rules": {
            "nearest_training_distance_threshold": threshold,
            "unsupported_topology": "mask signature absent from train112 -> excluded",
            "model_disagreement_threshold": "not applied to candidate pool; no response is available",
        },
        "candidate_pool_count": int(len(pool_angles)),
        "safe_count": int(np.sum(safe)),
        "safe_fraction": float(np.mean(safe)),
        "excluded_count": int(np.sum(~safe)),
        "excluded_fraction": float(np.mean(~safe)),
        "safe_indices": np.flatnonzero(safe).astype(int).tolist(),
        "excluded_reason_counts": {
            "nearest_distance": int(np.sum(distance > threshold)),
            "unsupported_topology": int(np.sum(~np.asarray([value in train_mask_signatures for value in pool_signatures]))),
        },
        "full_domain_model_lock": False,
        "validation_target_accessed": False,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return payload


def run_m4g(*, dataset_dir: Path, output_dir: Path, folds_path: Path,
            windows_path: Path, candidate_pool: Path, plan_path: Path,
            implementation_sha: str) -> dict[str, Any]:
    manifest = verify_immutable_package(dataset_dir,
                                        expected_dataset_id="task004_angle_nominal_p5_ny4_train112_v1")
    data = load_training_dataset(dataset_dir)
    angles = np.asarray(data["angles.npy"], dtype=np.float64)
    aggregates = np.asarray(data["aggregates.npy"], dtype=np.float64)
    masks = np.asarray(data["power_carrying_mask.npy"], dtype=bool)
    freeze_train112_reference_folds(dataset_dir=dataset_dir, output=folds_path,
                                    implementation_sha=implementation_sha)
    split = folds(angle_features(angles, "F1"), n_splits=5, seed=FOLD_SEED)
    windows = _load_windows(windows_path, angles, manifest["training_tuple_sha256"])
    plan = json.loads(plan_path.read_text())
    base_results = {spec["candidate"]: _base_result(spec, angles, aggregates, split, windows)
                    for spec in LOCAL_SPECS}
    ensembles = _build_ensembles(angles, aggregates, split, base_results, windows)
    all_results = {**base_results, **ensembles}
    ranked = sorted(all_results.values(), key=lambda item: (item["selection_score"], item["candidate"]))
    selected = ranked[0]
    oof_records = _make_oof_records(angles, aggregates, masks, split, all_results, plan)
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison = {
        "schema_version": "task004.train112-local-model-comparison.v1",
        "dataset_id": manifest["dataset_id"],
        "training_tuple_sha256": manifest["training_tuple_sha256"],
        "forward_solver_sha": manifest["forward_solver_sha"],
        "surrogate_training_code_sha": implementation_sha,
        "folds_file": str(folds_path), "fold_seed": FOLD_SEED,
        "candidate_set": list(all_results),
        "selected_candidate_by_training_cv": selected["candidate"],
        "candidate_results": [_summary(result) for result in ranked],
        "validation_target_accessed": False,
    }
    (output_dir / "TRAIN112_LOCAL_MODEL_COMPARISON.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True, allow_nan=False) + "\n")
    (output_dir / "TRAIN112_LOCAL_OOF.json").write_text(
        json.dumps({"schema_version": "task004.train112-local-oof.v1",
                    "dataset_id": manifest["dataset_id"],
                    "candidate_set": list(all_results), "records": oof_records,
                    "validation_target_accessed": False},
                   indent=2, sort_keys=True, allow_nan=False) + "\n")
    lines = ["# TRAIN112 local candidate comparison", "",
             "All results use the frozen 112-row outer folds and training-only response.", "",
             "| candidate | R NRMSE | T NRMSE | A NRMSE | max Gate score | supported-window Gate | uncertainty Gate | Aggregate Level A |", "|---|---:|---:|---:|---:|---|---|---|"]
    for result in ranked:
        lines.append(f"| {result['candidate']} | {result['metrics']['R_total']['nrmse']:.8g} | {result['metrics']['T_total']['nrmse']:.8g} | {result['metrics']['A_balance']['nrmse']:.8g} | {result['selection_score']:.8g} | {result.get('supported_window_gate')} | {result['uncertainty'].get('gate')} | {result.get('aggregate_qualified')} |")
    lines += ["", f"Training-CV selection is `{selected['candidate']}`.  No model lock is created unless all Aggregate Level A gates pass."]
    (output_dir / "TRAIN112_LOCAL_MODEL_COMPARISON.md").write_text("\n".join(lines) + "\n")
    build_outlier_audit(angles=angles, aggregates=aggregates, masks=masks,
                        base_results=base_results, all_results=all_results,
                        oof_records=oof_records, plan=plan,
                        output_json=output_dir / "POST_ACTIVE_OUTLIER_AUDIT.json",
                        output_md=output_dir / "POST_ACTIVE_OUTLIER_AUDIT.md",
                        implementation_sha=implementation_sha)
    safe = None
    if not any(result["aggregate_qualified"] for result in all_results.values()):
        safe = build_safe_domain_candidate(
            dataset_dir=dataset_dir, angles=angles, masks=masks,
            base_results=base_results, candidate_pool=candidate_pool,
            output=output_dir / "ANGLE_AGGREGATE_SAFE_DOMAIN_CANDIDATE.json",
            implementation_sha=implementation_sha,
        )
    return {"comparison": comparison, "selected": selected,
            "all_results": all_results, "safe_domain": safe,
            "oof_records": oof_records}
