"""Task006 M2R: auditable, S0-authoritative training-only qualification.

This module deliberately keeps the original M2 outputs immutable.  M2R uses
the same six finite candidates, but production S1 no longer fits an
independent side-total model: S0's composition prediction is the only source
of the reflection/transmission side totals.  Only the selected-channel
fraction is learned from S1 data.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize

from ..models import ExactARDGP, OrthogonalPCE, TrendResidualGP
from .dataset import EPSILON, load_dataset
from .design import (
    ANGLES,
    BLIND_GEOMETRIES,
    FORWARD_SOLVER_SHA,
    MODEL_ID,
    OBSERVABLE_SCHEMA,
    ROUTE_ID,
    TASK006_DATASET_ID,
    TASK005_LOCK,
    canonical_hash,
    file_hash,
    TRAIN_GEOMETRIES,
)
from .surrogate import (
    FEATURE_MAX,
    FEATURE_MIN,
    LocalRBFModel,
    PolynomialModel,
    TrendModel,
    noise_sigma,
    sigmoid,
)


CANDIDATES = (
    "legendre_2",
    "legendre_3",
    "legendre_4",
    "local_rbf_k8",
    "matern52_ard_exact_gp",
    "degree2_trend_plus_matern52_residual",
)


def scale_geometry(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    return 2.0 * (values - FEATURE_MIN) / (FEATURE_MAX - FEATURE_MIN) - 1.0


def fold_indices(n: int = 37, n_splits: int = 5) -> list[tuple[np.ndarray, np.ndarray]]:
    """The frozen modulo folds; no random state is involved."""

    ids = np.arange(n, dtype=np.int64)
    return [(ids[ids % n_splits != fold], ids[ids % n_splits == fold])
            for fold in range(n_splits)]


def _array_hash(value: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(value, dtype=np.float64))
    descriptor = json.dumps({"dtype": str(array.dtype), "shape": list(array.shape)},
                            sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(descriptor + array.tobytes(order="C")).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.float64, np.float32, np.int64, np.int32, np.bool_)):
        return value.item()
    raise TypeError(type(value).__name__)


def _regions(geometry: np.ndarray) -> list[str]:
    return ["boundary" if h in (115.0, 125.0) or w in (16.0, 18.0)
            else "interior" for h, w in np.asarray(geometry)]


def write_fold_manifest(geometry: np.ndarray, outcomes: Path) -> dict[str, Any]:
    """Freeze folds, tuple membership and hashes before fitting any candidate."""

    folds = []
    regions = _regions(geometry)
    for fold, (train, test) in enumerate(fold_indices(len(geometry), 5)):
        row = {
            "fold": fold,
            "train_indices": train.tolist(),
            "test_indices": test.tolist(),
            "train_geometries": np.asarray(geometry[train]).tolist(),
            "test_geometries": np.asarray(geometry[test]).tolist(),
            "test_region_counts": {
                "boundary": int(sum(regions[i] == "boundary" for i in test)),
                "interior": int(sum(regions[i] == "interior" for i in test)),
            },
        }
        row["fold_tuple_sha256"] = canonical_hash({
            "fold": fold,
            "train": row["train_geometries"],
            "test": row["test_geometries"],
        })
        folds.append(row)
    payload = {
        "schema_version": "task006.train37-geometry-folds.v1",
        "status": "frozen",
        "dataset_id": TASK006_DATASET_ID,
        "geometry_count": int(len(geometry)),
        "n_splits": 5,
        "fold_rule": "test_indices = np.arange(37)[indices % 5 == fold]; all three angles remain grouped",
        "geometry_tuple_sha256": canonical_hash(np.asarray(geometry).tolist()),
        "folds": folds,
        "all_test_indices_once": sorted(i for row in folds for i in row["test_indices"]) == list(range(len(geometry))),
        "folds_sha256": canonical_hash(folds),
        "blind_response_accessed": False,
    }
    outcomes.mkdir(parents=True, exist_ok=True)
    (outcomes / "TRAIN37_GEOMETRY_FOLDS.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return payload


def _make_model(candidate: str, seed: int):
    if candidate.startswith("legendre_"):
        return PolynomialModel(int(candidate.split("_")[1]))
    if candidate == "local_rbf_k8":
        return LocalRBFModel(neighbors=8)
    if candidate == "matern52_ard_exact_gp":
        from .surrogate import ExactModel
        return ExactModel(seed=seed)
    if candidate == "degree2_trend_plus_matern52_residual":
        return TrendModel(seed=seed)
    raise ValueError(f"unknown Task006 candidate {candidate}")


def _fit_scalar(candidate: str, x_train: np.ndarray, y_train: np.ndarray,
                x_query: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray, dict[str, Any], Any]:
    model = _make_model(candidate, seed)
    model.fit(x_train, y_train)
    mean, std = model.predict(x_query)
    return np.asarray(mean, dtype=np.float64), np.maximum(np.asarray(std, dtype=np.float64), 1.0e-10), model.metadata(), model


def _fit_contract(candidate: str, geometry: np.ndarray, latent: np.ndarray,
                  fractions: np.ndarray, train: np.ndarray, query: np.ndarray,
                  seed: int) -> dict[str, Any]:
    """Fit S0 and S1 fractions, with S0 as the sole side-total authority."""

    x_train = scale_geometry(geometry[train])
    x_query = scale_geometry(query)
    n = len(query)
    latent_mean = np.empty((n, 3, 2)); latent_std = np.empty_like(latent_mean)
    fraction_mean = np.empty((n, 3, 2)); fraction_std = np.empty_like(fraction_mean)
    fits: list[dict[str, Any]] = []
    aggregate_models: list[Any] = []
    fraction_models: list[Any] = []
    for angle in range(3):
        for target in range(2):
            mean, std, metadata, model = _fit_scalar(
                candidate, x_train, latent[train, angle, target], x_query,
                seed + angle * 11 + target)
            latent_mean[:, angle, target] = mean
            latent_std[:, angle, target] = std
            aggregate_models.append(model)
            fits.append({"contract": "S0", "angle_index": angle,
                         "target_index": target, "metadata": metadata})
            logits = np.log((fractions[train, angle, target, 0] + EPSILON)
                            / (fractions[train, angle, target, 1] + EPSILON))
            mean, std, metadata, model = _fit_scalar(
                candidate, x_train, logits, x_query,
                seed + 200 + angle * 11 + target)
            fraction = sigmoid(mean)
            fraction_mean[:, angle, target] = fraction
            fraction_std[:, angle, target] = np.maximum(
                std * fraction * (1.0 - fraction), 1.0e-10)
            fraction_models.append(model)
            fits.append({"contract": "S1_fraction_logit", "angle_index": angle,
                         "target_index": target, "metadata": metadata})

    logits = np.concatenate([latent_mean, np.zeros((n, 3, 1))], axis=2)
    logits -= np.max(logits, axis=2, keepdims=True)
    weights = np.exp(logits)
    aggregate_prediction = weights / np.sum(weights, axis=2, keepdims=True)
    aggregate_std = np.maximum(
        np.max(latent_std, axis=2, keepdims=True) * np.ones_like(aggregate_prediction),
        1.0e-10)
    side_total = aggregate_prediction[:, :, :2]
    side_std = aggregate_std[:, :, :2]
    selected = side_total * fraction_mean
    other = side_total * (1.0 - fraction_mean)
    selected_std = np.sqrt((fraction_mean * side_std) ** 2
                           + (side_total * fraction_std) ** 2)
    other_std = np.sqrt(((1.0 - fraction_mean) * side_std) ** 2
                        + (side_total * fraction_std) ** 2)
    ledger = selected + other - side_total
    return {
        "aggregate_prediction": aggregate_prediction,
        "aggregate_std": aggregate_std,
        "side_total_authority": side_total,
        "side_total_std": side_std,
        "fraction_prediction": fraction_mean,
        "fraction_std": fraction_std,
        "selected_prediction": selected,
        "selected_std": selected_std,
        "other_prediction": other,
        "other_std": other_std,
        "ledger_residual": ledger,
        "fits": fits,
        "_models": {"aggregate": aggregate_models, "fraction": fraction_models},
    }


def _predict_fitted_contract(models: dict[str, list[Any]], query: np.ndarray) -> dict[str, np.ndarray]:
    x_query = scale_geometry(query)
    n = len(query)
    latent_mean = np.empty((n, 3, 2)); latent_std = np.empty_like(latent_mean)
    fraction_mean = np.empty((n, 3, 2)); fraction_std = np.empty_like(fraction_mean)
    for angle in range(3):
        for target in range(2):
            index = angle * 2 + target
            mean, std = models["aggregate"][index].predict(x_query)
            latent_mean[:, angle, target] = mean
            latent_std[:, angle, target] = np.maximum(std, 1.0e-10)
            mean, std = models["fraction"][index].predict(x_query)
            fraction = sigmoid(mean)
            fraction_mean[:, angle, target] = fraction
            fraction_std[:, angle, target] = np.maximum(
                std * fraction * (1.0 - fraction), 1.0e-10)
    logits = np.concatenate([latent_mean, np.zeros((n, 3, 1))], axis=2)
    logits -= np.max(logits, axis=2, keepdims=True)
    weights = np.exp(logits)
    aggregate = weights / np.sum(weights, axis=2, keepdims=True)
    aggregate_std = np.maximum(
        np.max(latent_std, axis=2, keepdims=True) * np.ones_like(aggregate),
        1.0e-10)
    side = aggregate[:, :, :2]
    side_std = aggregate_std[:, :, :2]
    selected = side * fraction_mean
    other = side * (1.0 - fraction_mean)
    selected_std = np.sqrt((fraction_mean * side_std) ** 2
                           + (side * fraction_std) ** 2)
    other_std = np.sqrt(((1.0 - fraction_mean) * side_std) ** 2
                        + (side * fraction_std) ** 2)
    return {
        "aggregate_prediction": aggregate,
        "aggregate_std": aggregate_std,
        "side_total_authority": side,
        "side_total_std": side_std,
        "fraction_prediction": fraction_mean,
        "fraction_std": fraction_std,
        "selected_prediction": selected,
        "selected_std": selected_std,
        "other_prediction": other,
        "other_std": other_std,
        "ledger_residual": selected + other - side,
    }


def _target_metrics(truth: np.ndarray, prediction: np.ndarray, std: np.ndarray,
                    mask: np.ndarray | None = None) -> dict[str, Any]:
    truth = np.asarray(truth, dtype=np.float64)
    prediction = np.asarray(prediction, dtype=np.float64)
    std = np.asarray(std, dtype=np.float64)
    if mask is not None:
        truth, prediction, std = truth[mask], prediction[mask], std[mask]
    error = prediction - truth
    scale = float(np.ptp(truth)) or 1.0
    sigma = noise_sigma(truth, "N1")
    normalized_error = np.abs(error) / sigma
    half_width = 1.96 * np.maximum(std, 1.0e-10)
    return {
        "n": int(error.size),
        "nrmse": float(np.sqrt(np.mean(error ** 2)) / scale),
        "p95_abs": float(np.percentile(np.abs(error), 95)),
        "max_abs": float(np.max(np.abs(error))),
        "p95_normalized_N1": float(np.percentile(normalized_error, 95)),
        "max_normalized_N1": float(np.max(normalized_error)),
        "coverage_95": float(np.mean(np.abs(error) <= half_width)),
        "p95_half_width": float(np.percentile(half_width, 95)),
        "p95_N1_sigma": float(np.percentile(sigma, 95)),
        "finite_positive_width": bool(np.all(np.isfinite(half_width)) and np.all(half_width > 0.0)),
    }


def _region_metrics(truth: np.ndarray, prediction: np.ndarray, std: np.ndarray,
                    regions: list[str]) -> dict[str, Any]:
    return {
        region: _target_metrics(truth, prediction, std,
                                np.asarray([item == region for item in regions]))
        for region in ("boundary", "interior")
    }


def _score(result: dict[str, Any]) -> float:
    values: list[float] = []
    for target in result["s0_metrics"].values():
        values.extend([target["nrmse"] / 0.01, target["p95_abs"] / 0.005,
                       target["max_abs"] / 0.015])
    for target in result["s1_metrics"].values():
        values.extend([target["nrmse"] / 0.02,
                       target["p95_normalized_N1"] / 0.75,
                       target["max_normalized_N1"] / 2.0])
    values.extend([1.0 / max(result["uncertainty"]["minimum_coverage"], 1.0e-12),
                   result["uncertainty"]["p95_width_over_N1_sigma"]])
    return float(max(values))


def _rows_for_candidate(candidate: str, geometry: np.ndarray, aggregates: np.ndarray,
                        selected_truth: np.ndarray, result: dict[str, Any],
                        fold_row: np.ndarray, regions: list[str], distances: np.ndarray) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    s0 = result["aggregate_prediction"]
    s0_std = result["aggregate_std"]
    side = result["side_total_authority"]
    selected = result["selected_prediction"]
    other = result["other_prediction"]
    selected_std = result["selected_std"]
    other_std = result["other_std"]
    ledger = result["ledger_residual"]
    other_truth = np.stack((aggregates[:, :, 0] - selected_truth[:, :, 0],
                            aggregates[:, :, 1] - selected_truth[:, :, 1]), axis=2)
    for index in range(len(geometry)):
        for angle in range(3):
            for target, name in enumerate(("R_total", "T_total", "A_balance")):
                rows.append({
                    "candidate": candidate, "contract": "S0",
                    "geometry_index": index, "geometry": geometry[index].tolist(),
                    "angle_index": angle, "target": name,
                    "truth": float(aggregates[index, angle, target]),
                    "prediction": float(s0[index, angle, target]),
                    "std": float(s0_std[index, angle, target]),
                    "error": float(s0[index, angle, target] - aggregates[index, angle, target]),
                    "fold": int(fold_row[index]), "region": regions[index],
                    "nearest_training_distance": float(distances[index]),
                })
            for target, name in enumerate(("reflection_m0_total", "transmission_m0_total")):
                rows.append({
                    "candidate": candidate, "contract": "S1",
                    "geometry_index": index, "geometry": geometry[index].tolist(),
                    "angle_index": angle, "target": name,
                    "truth": float(selected_truth[index, angle, target]),
                    "prediction": float(selected[index, angle, target]),
                    "std": float(selected_std[index, angle, target]),
                    "error": float(selected[index, angle, target] - selected_truth[index, angle, target]),
                    "fold": int(fold_row[index]), "region": regions[index],
                    "nearest_training_distance": float(distances[index]),
                    "s0_side_total_prediction": float(side[index, angle, target]),
                    "selected_prediction": float(selected[index, angle, target]),
                    "other_prediction": float(other[index, angle, target]),
                    "selected_plus_other": float(selected[index, angle, target] + other[index, angle, target]),
                    "ledger_residual": float(ledger[index, angle, target]),
                    "selected_nonnegative": bool(selected[index, angle, target] >= 0.0),
                    "other_nonnegative": bool(other[index, angle, target] >= 0.0),
                    "selected_le_side": bool(selected[index, angle, target] <= side[index, angle, target] + 1.0e-12),
                    "truth_side_total": float(aggregates[index, angle, target]),
                    "truth_other": float(other_truth[index, angle, target]),
                })
    return rows


def synthetic_recovery(candidate: str, geometry: np.ndarray, aggregates: np.ndarray,
                       selected_truth: np.ndarray, latent: np.ndarray,
                       fractions: np.ndarray, folds: list[tuple[np.ndarray, np.ndarray]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    h_grid = np.linspace(115.0, 125.0, 21)
    w_grid = np.linspace(16.0, 18.0, 21)
    fixed_starts = np.asarray([[115.0, 16.0], [115.0, 18.0], [125.0, 16.0],
                               [125.0, 18.0], [120.0, 17.0]], dtype=np.float64)
    for fold, (train, test) in enumerate(folds):
        fitted = _fit_contract(candidate, geometry, latent, fractions, train,
                               geometry[test], seed=900 + fold * 31)
        models = fitted["_models"]
        for index in test:
            def predict_at(point: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
                query = np.asarray(point, dtype=np.float64).reshape(1, 2)
                block = _predict_fitted_contract(models, query)
                return block["aggregate_prediction"][0], block["selected_prediction"][0]

            truth_s0 = aggregates[index]
            truth_s1 = selected_truth[index]
            sigma_s0 = noise_sigma(truth_s0, "N1")
            sigma_s1 = noise_sigma(truth_s1, "N1")

            def objective(point: np.ndarray, mode: str) -> float:
                prediction_s0, prediction_s1 = predict_at(point)
                if mode == "S1_N1":
                    return float(np.sum(((prediction_s1 - truth_s1) / sigma_s1) ** 2))
                if mode == "S0_N1":
                    return float(np.sum(((prediction_s0 - truth_s0) / sigma_s0) ** 2))
                if mode == "S0_N2":
                    return float(np.sum(((prediction_s0 - truth_s0) / noise_sigma(truth_s0, "N2")) ** 2))
                return float(np.sum(((prediction_s1 - truth_s1) / noise_sigma(truth_s1, "N2")) ** 2))

            grid = np.asarray([[h, w] for h in h_grid for w in w_grid], dtype=np.float64)
            values = np.asarray([objective(point, "S1_N1") for point in grid])
            starts = list(fixed_starts) + [grid[int(np.argmin(values))]]
            attempts: list[tuple[Any, str]] = []
            attempt_rows: list[dict[str, Any]] = []
            for start in starts:
                result = minimize(lambda point: objective(point, "S1_N1"), start,
                                  method="L-BFGS-B", bounds=((115.0, 125.0), (16.0, 18.0)),
                                  options={"maxiter": 80, "ftol": 1.0e-12})
                attempts.append((result, "L-BFGS-B"))
                attempt_rows.append({"method": "L-BFGS-B", "start": np.asarray(start).tolist(),
                                     "success": bool(result.success), "status": int(result.status),
                                     "message": str(result.message), "objective": float(result.fun)})
                if not result.success:
                    fallback = minimize(lambda point: objective(point, "S1_N1"), start,
                                        method="Powell", bounds=((115.0, 125.0), (16.0, 18.0)),
                                        options={"maxiter": 200, "xtol": 1.0e-10, "ftol": 1.0e-12})
                    attempts.append((fallback, "Powell"))
                    attempt_rows.append({"method": "Powell", "start": np.asarray(start).tolist(),
                                         "success": bool(fallback.success), "status": int(fallback.status),
                                         "message": str(fallback.message), "objective": float(fallback.fun)})
            successful = [pair for pair in attempts if bool(pair[0].success)]
            best, method = min(successful if successful else attempts,
                               key=lambda pair: float(pair[0].fun))
            estimate = np.asarray(best.x, dtype=np.float64)
            errors = estimate - geometry[index]
            records.append({
                "fold": fold, "geometry_index": int(index),
                "truth_geometry": geometry[index].tolist(), "estimate": estimate.tolist(),
                "height_error_nm": float(errors[0]), "width_error_nm": float(errors[1]),
                "objective_S1_N1": float(best.fun), "optimizer_method": method,
                "optimizer_attempts": attempt_rows, "converged": bool(best.success),
                "rejected": bool(not best.success),
                "S0_N1_objective_at_estimate": objective(estimate, "S0_N1"),
                "S0_N2_objective_at_estimate": objective(estimate, "S0_N2"),
                "S1_N2_objective_at_estimate": objective(estimate, "S1_N2"),
            })
    height = np.abs(np.asarray([row["height_error_nm"] for row in records]))
    width = np.abs(np.asarray([row["width_error_nm"] for row in records]))
    summary = {
        "p95_abs_height_nm": float(np.percentile(height, 95)),
        "p95_abs_width_nm": float(np.percentile(width, 95)),
        "max_abs_height_nm": float(np.max(height)),
        "max_abs_width_nm": float(np.max(width)),
        "rejected_count": int(sum(row["rejected"] for row in records)),
    }
    return {
        "schema_version": "task006.train37-synthetic-recovery-v2",
        "candidate": candidate, "records": records, "summary": summary,
        "hard_gate": bool(summary["p95_abs_height_nm"] <= 0.25
                           and summary["p95_abs_width_nm"] <= 0.05
                           and summary["max_abs_height_nm"] <= 0.50
                           and summary["max_abs_width_nm"] <= 0.10
                           and summary["rejected_count"] == 0),
        "training_only": True, "test_truth_used_only_as_synthetic_observation": True,
        "blind_response_accessed": False,
    }


def _fit_metric_bundle(truth: np.ndarray, prediction: np.ndarray,
                       std: np.ndarray, names: tuple[str, ...],
                       regions: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    all_metrics: dict[str, Any] = {}
    regional: dict[str, Any] = {}
    for target, name in enumerate(names):
        all_metrics[name] = _target_metrics(truth[:, target], prediction[:, target], std[:, target])
        regional[name] = _region_metrics(truth[:, target], prediction[:, target], std[:, target], regions)
    return all_metrics, regional


def run_m2r(*, dataset_root: Path, outcomes: Path) -> dict[str, Any]:
    data = load_dataset(dataset_root)
    geometry = np.asarray(data["geometries"], dtype=np.float64)
    aggregates = np.asarray(data["aggregates"][:, :, :3], dtype=np.float64)
    latent = np.asarray(data["aggregate_latent"], dtype=np.float64)
    fractions = np.asarray(data["s1_fractions"], dtype=np.float64)
    selected_truth = np.asarray(data["s1_selected_powers"], dtype=np.float64)
    folds = fold_indices(len(geometry), 5)
    fold_manifest = write_fold_manifest(geometry, outcomes)
    regions = _regions(geometry)
    fold_row = np.full(len(geometry), -1, dtype=np.int64)
    distances = np.full(len(geometry), np.nan, dtype=np.float64)
    for fold, (train, test) in enumerate(folds):
        fold_row[test] = fold
        train_scaled = scale_geometry(geometry[train])
        distances[test] = [float(np.min(np.linalg.norm(train_scaled - row, axis=1)))
                           for row in scale_geometry(geometry[test])]

    comparison: dict[str, Any] = {}
    candidate_runs: dict[str, dict[str, Any]] = {}
    for candidate in CANDIDATES:
        s0_pred = np.full((len(geometry), 3, 3), np.nan)
        s0_std = np.full_like(s0_pred, np.nan)
        side_pred = np.full((len(geometry), 3, 2), np.nan)
        side_std = np.full_like(side_pred, np.nan)
        selected_pred = np.full_like(side_pred, np.nan)
        selected_std = np.full_like(side_pred, np.nan)
        other_pred = np.full_like(side_pred, np.nan)
        other_std = np.full_like(side_pred, np.nan)
        ledger = np.full_like(side_pred, np.nan)
        fit_records: list[dict[str, Any]] = []
        for fold, (train, test) in enumerate(folds):
            block = _fit_contract(candidate, geometry, latent, fractions, train,
                                  geometry[test], seed=700 + fold * 97)
            s0_pred[test] = block["aggregate_prediction"]
            s0_std[test] = block["aggregate_std"]
            side_pred[test] = block["side_total_authority"]
            side_std[test] = block["side_total_std"]
            selected_pred[test] = block["selected_prediction"]
            selected_std[test] = block["selected_std"]
            other_pred[test] = block["other_prediction"]
            other_std[test] = block["other_std"]
            ledger[test] = block["ledger_residual"]
            fit_records.extend([{**fit, "fold": fold} for fit in block["fits"]])

        s0_metrics, s0_region = _fit_metric_bundle(
            aggregates.reshape(len(geometry) * 3, 3),
            s0_pred.reshape(len(geometry) * 3, 3),
            s0_std.reshape(len(geometry) * 3, 3),
            ("R_total", "T_total", "A_balance"),
            [regions[index] for index in range(len(geometry)) for _ in range(3)])
        # Per-angle metrics are primary; the flattened aggregate is retained as
        # a compact cross-angle diagnostic.
        s0_metrics = {
            f"A{angle}_{name}": _target_metrics(
                aggregates[:, angle, target], s0_pred[:, angle, target], s0_std[:, angle, target])
            for angle in range(3) for target, name in enumerate(("R_total", "T_total", "A_balance"))
        }
        s0_region = {
            f"A{angle}_{name}": _region_metrics(
                aggregates[:, angle, target], s0_pred[:, angle, target], s0_std[:, angle, target], regions)
            for angle in range(3) for target, name in enumerate(("R_total", "T_total", "A_balance"))
        }
        s1_metrics = {
            f"A{angle}_{name}": _target_metrics(
                selected_truth[:, angle, target], selected_pred[:, angle, target], selected_std[:, angle, target])
            for angle in range(3) for target, name in enumerate(("reflection_m0_total", "transmission_m0_total"))
        }
        s1_region = {
            f"A{angle}_{name}": _region_metrics(
                selected_truth[:, angle, target], selected_pred[:, angle, target], selected_std[:, angle, target], regions)
            for angle in range(3) for target, name in enumerate(("reflection_m0_total", "transmission_m0_total"))
        }
        coverage_metrics = list(s0_metrics.values()) + list(s1_metrics.values())
        uncertainty = {
            "minimum_coverage": float(min(item["coverage_95"] for item in coverage_metrics)),
            "p95_width_over_N1_sigma": float(max(item["p95_half_width"] / max(item["p95_N1_sigma"], 1.0e-12)
                                                 for item in coverage_metrics)),
            "all_widths_finite_positive": bool(all(item["finite_positive_width"] for item in coverage_metrics)),
        }
        ledger_max = float(np.max(np.abs(ledger)))
        physics = {
            "s0_composition_max_abs_residual": float(np.max(np.abs(np.sum(s0_pred, axis=2) - 1.0))),
            "s1_selected_min": float(np.min(selected_pred)),
            "s1_other_min": float(np.min(other_pred)),
            "s1_selected_le_side": bool(np.all(selected_pred <= side_pred + 1.0e-12)),
            "s1_ledger_max_abs_residual": ledger_max,
            "s1_ledger_exact": bool(ledger_max <= 1.0e-12),
            "side_total_authority": "S0 predicted R_total/T_total",
        }
        hard_gate = bool(
            all(item["nrmse"] <= 0.01 and item["p95_abs"] <= 0.005 and item["max_abs"] <= 0.015
                for item in s0_metrics.values())
            and physics["s0_composition_max_abs_residual"] <= 1.0e-12
            and all(item["nrmse"] <= 0.02 and item["p95_normalized_N1"] <= 0.75
                    and item["max_normalized_N1"] <= 2.0 for item in s1_metrics.values())
            and physics["s1_selected_min"] >= 0.0 and physics["s1_other_min"] >= 0.0
            and physics["s1_selected_le_side"] and physics["s1_ledger_exact"]
            and uncertainty["minimum_coverage"] >= 0.90
            and uncertainty["all_widths_finite_positive"]
            and uncertainty["p95_width_over_N1_sigma"] <= 1.0)
        result = {
            "candidate": candidate, "s0_metrics": s0_metrics, "s0_region_metrics": s0_region,
            "s1_metrics": s1_metrics, "s1_region_metrics": s1_region,
            "uncertainty": uncertainty, "physics": physics, "hard_gate": hard_gate,
            "selection_score": 0.0, "fit_records": fit_records,
            "prediction_hash": _array_hash(np.concatenate((s0_pred, side_pred, selected_pred,
                                                            other_pred, ledger), axis=2)),
        }
        result["selection_score"] = _score(result)
        comparison[candidate] = result
        candidate_runs[candidate] = {
            "aggregate_prediction": s0_pred, "aggregate_std": s0_std,
            "side_total_authority": side_pred, "side_total_std": side_std,
            "selected_prediction": selected_pred, "selected_std": selected_std,
            "other_prediction": other_pred, "other_std": other_std,
            "ledger_residual": ledger,
        }

    eligible = [candidate for candidate in CANDIDATES if comparison[candidate]["hard_gate"]]
    selected_candidate = min(eligible or list(CANDIDATES),
                             key=lambda name: comparison[name]["selection_score"])
    selected = candidate_runs[selected_candidate]
    rows = _rows_for_candidate(selected_candidate, geometry, aggregates, selected_truth,
                               selected, fold_row, regions, distances)
    recovery = synthetic_recovery(selected_candidate, geometry, aggregates, selected_truth,
                                  latent, fractions, folds)
    prediction_hash = comparison[selected_candidate]["prediction_hash"]
    model_selection = {
        "schema_version": "task006.training-model-selection-candidate-v2",
        "status": "m2r_training_qualified_pending_lock" if eligible and recovery["hard_gate"] else "m2r_controlled_negative",
        "selected_candidate": selected_candidate,
        "selection_basis": "minimum training-only grouped-CV selection_score among the fixed six candidates",
        "eligible_candidates": eligible,
        "candidate_scores": {name: comparison[name]["selection_score"] for name in CANDIDATES},
        "selected_prediction_hash": prediction_hash,
        "folds_sha256": fold_manifest["folds_sha256"],
        "training_only": True,
        "synthetic_recovery": recovery["hard_gate"],
        "blind_response_accessed": False,
        "validation_target_accessed": False,
    }
    outcomes.mkdir(parents=True, exist_ok=True)
    (outcomes / "TRAIN37_MODEL_COMPARISON_V2.json").write_text(json.dumps({
        "schema_version": "task006.train37-model-comparison-v2",
        "dataset_id": TASK006_DATASET_ID, "forward_solver_sha": FORWARD_SOLVER_SHA,
        "fixed_angle_order": [angle[0] for angle in ANGLES], "folds_sha256": fold_manifest["folds_sha256"],
        "candidates": comparison, "selected_candidate": selected_candidate,
        "training_only": True, "blind_response_accessed": False,
    }, indent=2, ensure_ascii=False, default=_json_default) + "\n")
    (outcomes / "TRAIN37_OOF_PREDICTIONS_V2.json").write_text(json.dumps({
        "schema_version": "task006.train37-oof-v2", "candidate": selected_candidate,
        "prediction_hash": prediction_hash, "records": rows, "training_only": True,
        "blind_response_accessed": False,
    }, indent=2, ensure_ascii=False) + "\n")
    ledger_rows = [row for row in rows if row["contract"] == "S1"]
    (outcomes / "TRAIN37_S1_LEDGER_V2.json").write_text(json.dumps({
        "schema_version": "task006.train37-s1-ledger-v2", "candidate": selected_candidate,
        "side_total_authority": "S0 predicted R_total/T_total", "records": ledger_rows,
        "max_abs_ledger_residual": float(np.max(np.abs(selected["ledger_residual"]))),
        "training_only": True, "blind_response_accessed": False,
    }, indent=2, ensure_ascii=False) + "\n")
    (outcomes / "TRAIN37_UNCERTAINTY_V2.json").write_text(json.dumps({
        "schema_version": "task006.train37-uncertainty-v2", "candidate": selected_candidate,
        "uncertainty": comparison[selected_candidate]["uncertainty"],
        "target_metrics": {"s0": comparison[selected_candidate]["s0_metrics"],
                           "s1": comparison[selected_candidate]["s1_metrics"]},
        "cross_fitted": True, "training_only": True, "blind_response_accessed": False,
    }, indent=2, ensure_ascii=False) + "\n")
    (outcomes / "TRAIN37_SYNTHETIC_RECOVERY_V2.json").write_text(
        json.dumps(recovery, indent=2, ensure_ascii=False) + "\n")
    (outcomes / "TRAINING_MODEL_SELECTION_CANDIDATE_V2.json").write_text(
        json.dumps(model_selection, indent=2, ensure_ascii=False) + "\n")
    return model_selection
