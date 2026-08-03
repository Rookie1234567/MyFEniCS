"""Task004 Required M4E2 diagnostics and response-blind acquisition.

This module deliberately stops before any forward solve.  It consumes the
immutable train96 response package plus the angle-only candidate/validation
designs.  It provides a geometry audit for interpolation windows, OOF error
maps, finite F1/F4 local Matérn comparisons, acquisition-quality statistics,
and a deterministic 16-point response-blind plan.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
from scipy.spatial import Delaunay, QhullError
from scipy.stats import spearmanr

from ..folds import FOLD_SEED, fold_identity, folds
from .dataset import load_training_dataset, verify_immutable_package
from .m4e import (
    F3_LOCAL_FEATURE,
    TARGETS,
    _crossfit_calibration,
    _hash,
    _inner_radius,
    _make_candidate,
    _metrics,
)
from .models import (
    analytic_power_carrying_mask,
    angle_features,
    cutoff_identity,
    region_masks,
)


M4E2_FEATURE_CANDIDATES = ("F1", "F4")
M4E2_WEIGHTS = {
    "native_std": 0.35,
    "matern_k24_k32_disagreement": 0.25,
    "rbf_matern_disagreement": 0.20,
    "nearest_training_distance": 0.10,
    "cutoff_topology_bonus": 0.10,
}
M4E2_CANDIDATE_SPECS = (
    {"candidate": "L1_local_rbf_k24_s1e-08", "family": "local_rbf",
     "neighbors": 24, "smoothing": 1.0e-8, "feature": "F1"},
    {"candidate": "L2_local_matern_k24", "family": "local_matern",
     "neighbors": 24, "jitter": 1.0e-8, "feature": "F1"},
    {"candidate": "L2_local_matern_k32", "family": "local_matern",
     "neighbors": 32, "jitter": 1.0e-8, "feature": "F1"},
    {"candidate": "L4_trend_local_residual_k32", "family": "trend_local_residual",
     "neighbors": 32, "smoothing": 1.0e-8, "feature": "F1"},
    {"candidate": "L2_local_matern_f4_k24", "family": "local_matern",
     "neighbors": 24, "jitter": 1.0e-8, "feature": "F4"},
    {"candidate": "L2_local_matern_f4_k32", "family": "local_matern",
     "neighbors": 32, "jitter": 1.0e-8, "feature": "F4"},
)
WINDOW_NAMES = ("low_grazing", "high_azimuth", "cutoff_near", "ordinary_interior")


def _canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def _read_design(path: Path) -> tuple[dict[str, Any], np.ndarray, list[list[float]]]:
    data = json.loads(path.read_text())
    tuples = [[float(np.round(float(point[key]), 12)) for key in
               ("height_nm", "width_x_nm", "grazing_deg", "azimuth_deg")]
              for point in data["points"]]
    angles = np.asarray([[row[2], row[3]] for row in tuples], dtype=np.float64)
    return data, angles, tuples


def _domain_boundary_edges(point: np.ndarray, tolerance: float = 1.0e-10) -> list[str]:
    grazing, azimuth = map(float, point)
    edges: list[str] = []
    if abs(grazing - 0.5) <= tolerance:
        edges.append("grazing_min")
    if abs(grazing - 10.0) <= tolerance:
        edges.append("grazing_max")
    if abs(azimuth - 0.0) <= tolerance:
        edges.append("azimuth_min")
    if abs(azimuth - 90.0) <= tolerance:
        edges.append("azimuth_max")
    return edges


def _geometry_support(query: np.ndarray, support: np.ndarray) -> dict[str, Any]:
    """Classify support without trusting a stored status flag.

    Interior support requires a query in the support convex hull and at least
    three angular sectors.  Domain-boundary support is one-sided in the inward
    normal but spans the boundary tangent and has rank-two local geometry.
    """

    query = np.asarray(query, dtype=np.float64)
    support = np.asarray(support, dtype=np.float64)
    query_feature = angle_features(query[None, :], "F1")[0]
    support_feature = angle_features(support, "F1")
    vectors = support_feature - query_feature[None, :]
    distances = np.linalg.norm(vectors, axis=1)
    sectors = np.unique(np.floor((np.arctan2(vectors[:, 1], vectors[:, 0]) + np.pi) /
                                 (np.pi / 4.0)).astype(int))
    convex_hull_contains = False
    hull_error = None
    if len(support_feature) >= 3 and np.linalg.matrix_rank(support_feature - support_feature[0]) >= 2:
        try:
            convex_hull_contains = bool(Delaunay(support_feature).find_simplex(query_feature) >= 0)
        except QhullError as exc:
            hull_error = str(exc)
    edges = _domain_boundary_edges(query)
    inward_counts: dict[str, int] = {}
    tangent_spans: dict[str, float] = {}
    for edge in edges:
        if edge == "grazing_min":
            inward = support[:, 0] - query[0]
            tangent = support[:, 1] - query[1]
        elif edge == "grazing_max":
            inward = query[0] - support[:, 0]
            tangent = support[:, 1] - query[1]
        elif edge == "azimuth_min":
            inward = support[:, 1] - query[1]
            tangent = support[:, 0] - query[0]
        else:
            inward = query[1] - support[:, 1]
            tangent = support[:, 0] - query[0]
        inward_counts[edge] = int(np.sum(inward > 1.0e-8))
        tangent_spans[edge] = float(np.ptp(tangent))
    boundary_supported = bool(
        edges and all(inward_counts[edge] >= 2 and tangent_spans[edge] >= 0.02
                      for edge in edges)
    )
    if edges and boundary_supported:
        classification = "boundary_one_sided_supported"
    elif convex_hull_contains and len(sectors) >= 3:
        classification = "interior_bracketed"
    else:
        classification = "unsupported_extrapolation"
    return {
        "classification": classification,
        "convex_hull_contains": convex_hull_contains,
        "hull_error": hull_error,
        "direction_sector_count": int(len(sectors)),
        "direction_sectors": sectors.astype(int).tolist(),
        "boundary_edges": edges,
        "inward_support_counts": inward_counts,
        "tangent_spans": tangent_spans,
        "local_rank": int(np.linalg.matrix_rank(vectors)) if len(vectors) else 0,
        "nearest_support_distance": float(np.min(distances)) if len(distances) else float("inf"),
    }


def freeze_supported_interpolation_windows_v3(*, angles: np.ndarray, v2_path: Path,
                                              output: Path, dataset_id: str,
                                              training_tuple_sha256: str,
                                              stress_authority: Path,
                                              implementation_sha: str) -> dict[str, Any]:
    """Create V3 while retaining V2 as immutable authority."""

    if output.is_file():
        cached = json.loads(output.read_text())
        if cached.get("surrogate_training_code_sha") == implementation_sha:
            return cached
    v2 = json.loads(v2_path.read_text())
    if v2.get("training_tuple_sha256") != training_tuple_sha256:
        raise ValueError("V2 window tuple hash does not match train96")
    values = np.asarray(angles, dtype=np.float64)
    windows = []
    for item in v2["windows"]:
        holdout = np.asarray(item["indices"], dtype=np.int64)
        support_idx = np.asarray(item["support_indices"], dtype=np.int64)
        query_feature = angle_features(values[holdout], "F1")
        support_feature = angle_features(values[support_idx.reshape(-1)], "F1").reshape(
            support_idx.shape + (2,)
        )
        # Recompute nearest distances from the sorted support identity; do not
        # reuse V2's erroneous distances.
        nearest = np.linalg.norm(support_feature - query_feature[:, None, :], axis=2)[:, 0]
        support_rows = []
        for row, index in enumerate(holdout):
            geometry = _geometry_support(values[index], values[support_idx[row]])
            support_rows.append({
                "index": int(index),
                "tuple": values[index].round(12).tolist(),
                "support_indices": support_idx[row].astype(int).tolist(),
                "support_coordinates": values[support_idx[row]].round(12).tolist(),
                "support_feature_coordinates": support_feature[row].tolist(),
                "nearest_support_distance": float(nearest[row]),
                **geometry,
            })
        supported_count = sum(row["classification"] != "unsupported_extrapolation"
                              for row in support_rows)
        windows.append({
            "name": item["name"], "indices": holdout.astype(int).tolist(),
            "tuples": values[holdout].round(12).tolist(), "count": int(len(holdout)),
            "support_indices": support_idx.astype(int).tolist(),
            "support_coordinates": values[support_idx].round(12).tolist(),
            "support_feature_coordinates": support_feature.tolist(),
            "nearest_support_distance": nearest.tolist(),
            "support_count_per_point": [int(len(row)) for row in support_idx],
            "support_rows": support_rows,
            "supported_count": int(supported_count),
            "advisory_count": int(len(support_rows) - supported_count),
            "hard_interpolation_gate": bool(supported_count == len(support_rows)),
            "cutoff_orders": item.get("cutoff_orders"),
            "signed_cutoff_margins": item.get("signed_cutoff_margins"),
            "window_sha256": _hash({"indices": holdout.tolist(),
                                     "tuples": values[holdout].round(12).tolist()}),
        })
    stress_hash = hashlib.sha256(stress_authority.read_bytes()).hexdigest()
    payload = {
        "schema_version": "task004.supported-interpolation-windows.v3",
        "dataset_id": dataset_id,
        "surrogate_training_code_sha": implementation_sha,
        "training_tuple_sha256": training_tuple_sha256,
        "support_feature": "F1_scaled_angle_coordinates",
        "windows": windows,
        "windows_sha256": _hash(windows),
        "v2_authority": {"path": str(v2_path), "sha256": hashlib.sha256(v2_path.read_bytes()).hexdigest(),
                         "schema_version": v2.get("schema_version")},
        "stress_authority": {"path": str(stress_authority), "sha256": stress_hash,
                              "schema_version": json.loads(stress_authority.read_text()).get("schema_version"),
                              "status": "advisory_extrapolation_stress"},
        "classification_contract": {
            "interior_bracketed": "hard_supported",
            "boundary_one_sided_supported": "hard_supported",
            "unsupported_extrapolation": "advisory_only",
            "checker_recomputes_from_coordinates": True,
        },
        "frozen_before_model_fitting": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def _labels_and_signature(angles: np.ndarray) -> tuple[list[str], list[str], np.ndarray, np.ndarray]:
    values = np.asarray(angles, dtype=np.float64)
    masks = region_masks(values)
    labels = ["+".join(name for name, mask in masks.items() if bool(mask[row]))
              for row in range(len(values))]
    mask = analytic_power_carrying_mask(values)
    signatures = [";".join(map(str, np.flatnonzero(mask[row]))) for row in range(len(values))]
    orders, margins = cutoff_identity(values)
    return labels, signatures, orders, margins


def _calibrated_std(truth: np.ndarray, prediction: np.ndarray, raw_std: np.ndarray,
                    split: list[tuple[np.ndarray, np.ndarray]]) -> tuple[np.ndarray, dict[str, Any]]:
    raw_std = np.maximum(np.asarray(raw_std, dtype=np.float64), 1.0e-12)
    standardized = np.abs(prediction - truth) / raw_std
    calibrated = np.full_like(raw_std, np.nan)
    factors = []
    for fold, (_, test) in enumerate(split):
        other = np.concatenate([split[k][1] for k in range(len(split)) if k != fold])
        factor = np.maximum(1.0, np.percentile(standardized[other], 95, axis=0) / 1.96)
        calibrated[test] = raw_std[test] * factor[None, :]
        factors.append({"fold": fold, "factor_by_target": {
            target: float(factor[i]) for i, target in enumerate(TARGETS)
        }, "source_outer_folds": [k for k in range(len(split)) if k != fold]})
    coverage = {target: float(np.mean(np.abs(prediction[:, i] - truth[:, i]) /
                                      np.maximum(calibrated[:, i], 1.0e-12) <= 1.96))
                for i, target in enumerate(TARGETS)}
    return calibrated, {
        "raw_coverage_95": {target: float(np.mean(standardized[:, i] <= 1.96))
                            for i, target in enumerate(TARGETS)},
        "cross_fitted_coverage_95": coverage,
        "fold_factors": factors,
        "gate": bool(all(0.90 <= value <= 0.99 for value in coverage.values())),
    }


def _distance_to_training(query: np.ndarray, train: np.ndarray, feature: str) -> np.ndarray:
    q = angle_features(query, feature); t = angle_features(train, feature)
    return np.min(np.linalg.norm(q[:, None, :] - t[None, :, :], axis=2), axis=1)


def _evaluate_oof_candidate(spec: dict[str, Any], angles: np.ndarray,
                            truth: np.ndarray, split: list[tuple[np.ndarray, np.ndarray]],
                            windows: dict[str, Any]) -> dict[str, Any]:
    prediction = np.full_like(truth, np.nan)
    raw_std = np.full_like(truth, np.nan)
    native_std = np.full_like(truth, np.nan)
    distance = np.full(len(angles), np.nan)
    point_rows: dict[str, Any] = {}
    fold_rows = []
    labels, signatures, cutoff_orders, cutoff_margins = _labels_and_signature(angles)
    for fold, (train, test) in enumerate(split):
        model = _make_candidate(spec).fit(angles[train], truth[train])
        mean, model_std = model.predict(angles[test])
        radius = _inner_radius(spec, angles[train], truth[train])
        floor = radius[None, :] / 1.96
        native = np.asarray(model_std, dtype=np.float64)
        if np.all(np.isfinite(native)):
            std = np.maximum(native, floor)
            native_std[test] = native
        else:
            std = np.broadcast_to(floor, mean.shape).copy()
            native_std[test] = np.nan
        prediction[test] = mean; raw_std[test] = std
        distance[test] = _distance_to_training(angles[test], angles[train], spec["feature"])
        for local, index in enumerate(test):
            point_rows[str(int(index))] = {
                "angle": angles[index].round(12).tolist(),
                "truth": truth[index].tolist(), "prediction": mean[local].tolist(),
                "error": (mean[local] - truth[index]).tolist(),
                "absolute_error": np.abs(mean[local] - truth[index]).tolist(),
                "predictive_std": std[local].tolist(),
                "native_std": native[local].tolist() if np.all(np.isfinite(native[local])) else None,
                "inner_conformal_radius": radius.tolist(), "fold": int(fold),
                "nearest_fold_training_distance": float(distance[index]),
                "cutoff_order": int(cutoff_orders[index]),
                "signed_cutoff_margin": float(cutoff_margins[index]),
                "mask_signature": signatures[index], "region_labels": labels[index],
                # ``LocalAggregateModel.diagnostics`` is one list per latent
                # channel; retain the exact neighbours used for this query
                # and channel rather than accidentally treating the outer
                # list as a row dictionary.
                "neighbor_indices": [
                    model.diagnostics[channel][local].get("neighbor_indices", [])
                    for channel in range(len(model.diagnostics))
                ],
                "model_unsupported": model.unsupported,
            }
        fold_rows.append({"fold": fold, "train_indices": train.tolist(),
                          "test_indices": test.tolist(), "inner_radius": radius.tolist(),
                          "model_metadata": model.metadata()})
    conformal, uncertainty = _calibrated_std(truth, prediction, raw_std, split)
    for index, row in point_rows.items():
        i = int(index)
        row["conformal_radius"] = conformal[i].tolist()
        row["standardized_residual"] = (np.abs(prediction[i] - truth[i]) /
                                         np.maximum(conformal[i], 1.0e-12)).tolist()
    metrics = {target: _metrics(truth[:, i], prediction[:, i])
               for i, target in enumerate(TARGETS)}
    region_metrics: dict[str, Any] = {}
    for name, region in region_masks(angles).items():
        region_metrics[name] = {target: _metrics(truth[region, i], prediction[region, i])
                                for i, target in enumerate(TARGETS)} if np.any(region) else {}
    supported_windows = {}
    for name, item in windows.items():
        holdout = np.asarray(item["indices"], dtype=np.int64)
        supported = np.asarray([row["index"] for row in item["support_rows"]
                                if row["classification"] != "unsupported_extrapolation"], dtype=np.int64)
        train = np.asarray([i for i in range(len(angles)) if i not in set(holdout)], dtype=np.int64)
        model = _make_candidate(spec).fit(angles[train], truth[train])
        estimate, _ = model.predict(angles[supported]) if len(supported) else (np.empty((0, 3)), None)
        supported_windows[name] = {
            "indices": holdout.tolist(), "supported_indices": supported.tolist(),
            "advisory_indices": [int(i) for i in holdout if i not in set(supported)],
            "metrics": {target: _metrics(truth[supported, i], estimate[:, i])
                         for i, target in enumerate(TARGETS)} if len(supported) else {},
            "hard_gate": bool(len(supported) and all(
                _metrics(truth[supported, i], estimate[:, i])["p95_abs"] <= 0.02
                for i in range(3)
            )),
        }
    hard_aggregate = bool(all(item["nrmse"] <= 0.01 and item["p95_abs"] <= 0.01 and
                              item["max_abs"] <= 0.03 for item in metrics.values()))
    supported_gate = bool(all(item["hard_gate"] for item in supported_windows.values()
                              if item["supported_indices"]))
    composition = bool(np.max(np.abs(np.sum(prediction, axis=1) - 1.0)) <= 1.0e-12)
    selection_score = float(max(max(item["nrmse"] / 0.01, item["p95_abs"] / 0.01,
                                      item["max_abs"] / 0.03) for item in metrics.values()))
    return {
        **spec, "metrics": metrics, "region_metrics": region_metrics,
        "uncertainty": uncertainty, "supported_windows": supported_windows,
        "aggregate_gate": hard_aggregate, "supported_window_gate": supported_gate,
        "composition_exact": composition, "aggregate_qualified": bool(
            hard_aggregate and supported_gate and composition and uncertainty["gate"]
        ), "selection_score": selection_score, "folds": fold_rows,
        "prediction": prediction, "raw_std": raw_std, "native_std": native_std,
        "conformal_std": conformal, "nearest_distance": distance,
        "point_rows": point_rows,
    }


def _scale(values: np.ndarray, bounds: tuple[float, float] | None = None) -> tuple[np.ndarray, tuple[float, float]]:
    values = np.asarray(values, dtype=np.float64)
    if bounds is None:
        bounds = (float(np.percentile(values, 5)), float(np.percentile(values, 95)))
    low, high = bounds
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        high = low + 1.0
    return np.clip((values - low) / (high - low), 0.0, 1.0), (low, high)


def _spearman(signal: np.ndarray, error: np.ndarray) -> float:
    if np.ptp(signal) == 0.0 or np.ptp(error) == 0.0:
        return 0.0
    value = spearmanr(signal, error).statistic
    return float(value) if np.isfinite(value) else 0.0


def _recall(signal: np.ndarray, error: np.ndarray, fraction: float = 0.20) -> float:
    count = max(1, int(np.ceil(len(signal) * fraction)))
    high_signal = set(np.argsort(signal, kind="mergesort")[-count:])
    high_error = set(np.argsort(error, kind="mergesort")[-count:])
    return float(len(high_signal & high_error) / len(high_error))


def _quality_row(signal: np.ndarray, absolute_error: np.ndarray) -> dict[str, Any]:
    top10 = set(np.argsort(absolute_error, kind="mergesort")[-10:])
    top20 = max(1, int(np.ceil(len(signal) * 0.20)))
    top_acq = set(np.argsort(signal, kind="mergesort")[-top20:])
    return {"spearman": _spearman(signal, absolute_error),
            "top20_error_recall": _recall(signal, absolute_error),
            "top10_error_covered_by_top20_acquisition": int(len(top10 & top_acq)),
            "top20_count": int(top20)}


def _acquisition_quality(results: dict[str, dict[str, Any]], angles: np.ndarray,
                         truth: np.ndarray) -> dict[str, Any]:
    rbf = results["L1_local_rbf_k24_s1e-08"]
    k24 = results["L2_local_matern_k24"]
    k32 = results["L2_local_matern_k32"]
    labels, signatures, orders, margins = _labels_and_signature(angles)
    counts: dict[str, int] = {}
    for signature in signatures:
        counts[signature] = counts.get(signature, 0) + 1
    rare = np.asarray([1.0 / np.sqrt(counts[signature]) for signature in signatures])
    cutoff_bonus = 1.0 / (np.abs(margins) + 0.005)
    topology_bonus, topology_bounds = _scale(rare)
    cutoff_scaled, cutoff_bounds = _scale(cutoff_bonus)
    geometry_bonus = np.clip(0.5 * topology_bonus + 0.5 * cutoff_scaled, 0.0, 1.0)
    components: dict[str, np.ndarray] = {
        "native_std_k24": np.nan_to_num(k24["native_std"], nan=0.0),
        "native_std_k32": np.nan_to_num(k32["native_std"], nan=0.0),
        "matern_k24_k32_disagreement": np.abs(k24["prediction"] - k32["prediction"]),
        "rbf_matern_disagreement": np.abs(rbf["prediction"] - k24["prediction"]),
        "nearest_training_distance": np.column_stack((k24["nearest_distance"],) * 3),
        "cutoff_topology_bonus": np.column_stack((geometry_bonus,) * 3),
    }
    signal_reports: dict[str, Any] = {}
    scale_bounds: dict[str, Any] = {}
    # Iterate over the original signal components only; the scaled arrays are
    # appended to ``components`` below and must not be visited recursively.
    for name, values in list(components.items()):
        rows = []
        for target_index, target in enumerate((*TARGETS, "max_error")):
            signal = values[:, target_index] if target != "max_error" else np.max(values, axis=1)
            error = (np.abs(k24["prediction"][:, target_index] - truth[:, target_index])
                     if target != "max_error" else np.max(
                         np.abs(k24["prediction"] - truth), axis=1))
            rows.append({"target": target, **_quality_row(signal, error)})
        signal_reports[name] = rows
        scaled, b = _scale(values)
        components[name + "_scaled"] = scaled
        scale_bounds[name] = {"low": b[0], "high": b[1]}
    # The weights are declared before any candidate-pool scoring and are used
    # identically for OOF audit and the eventual response-blind plan.
    ensemble = np.zeros((len(angles), 3), dtype=np.float64)
    ensemble += M4E2_WEIGHTS["native_std"] * components["native_std_k24_scaled"]
    ensemble += M4E2_WEIGHTS["matern_k24_k32_disagreement"] * components["matern_k24_k32_disagreement_scaled"]
    ensemble += M4E2_WEIGHTS["rbf_matern_disagreement"] * components["rbf_matern_disagreement_scaled"]
    ensemble += M4E2_WEIGHTS["nearest_training_distance"] * components["nearest_training_distance_scaled"]
    ensemble += M4E2_WEIGHTS["cutoff_topology_bonus"] * components["cutoff_topology_bonus_scaled"]
    ensemble_rows = []
    for target_index, target in enumerate((*TARGETS, "max_error")):
        signal = ensemble[:, target_index] if target != "max_error" else np.max(ensemble, axis=1)
        error = (np.abs(k24["prediction"][:, target_index] - truth[:, target_index])
                 if target != "max_error" else np.max(np.abs(k24["prediction"] - truth), axis=1))
        ensemble_rows.append({"target": target, **_quality_row(signal, error)})
    positive_signals = []
    for name, rows in {**signal_reports, "frozen_ensemble": ensemble_rows}.items():
        if any(row["spearman"] >= 0.30 or row["top20_error_recall"] >= 0.50 for row in rows):
            positive_signals.append(name)
    ensemble_non_antirelated = bool(all(row["spearman"] >= -0.20 for row in ensemble_rows))
    gate = bool(positive_signals and ensemble_non_antirelated)
    return {
        "schema_version": "task004.m4e2.acquisition-quality.v1",
        "weights": M4E2_WEIGHTS,
        "normalization_bounds": scale_bounds,
        "signal_reports": signal_reports,
        "frozen_ensemble_reports": ensemble_rows,
        "positive_signals": positive_signals,
        "ensemble_non_antirelated": ensemble_non_antirelated,
        "gate": gate,
        "acquisition_ensemble_oof": ensemble,
        "cutoff_order": orders.tolist(), "signed_cutoff_margin": margins.tolist(),
        "mask_signatures": signatures, "region_labels": labels,
    }


def _pool_model_predictions(spec: dict[str, Any], train_angles: np.ndarray,
                            train_truth: np.ndarray, pool_angles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    model = _make_candidate(spec).fit(train_angles, train_truth)
    return model.predict(pool_angles)


def _minmax_with_bounds(values: np.ndarray, bounds: dict[str, Any], name: str) -> np.ndarray:
    low = float(bounds[name]["low"]); high = float(bounds[name]["high"])
    return np.clip((np.asarray(values, dtype=np.float64) - low) / max(high - low, 1.0), 0.0, 1.0)


def _plan_points(*, train_angles: np.ndarray, train_truth: np.ndarray,
                 validation_tuples: list[list[float]], pool_data: dict[str, Any],
                 pool_angles: np.ndarray, quality: dict[str, Any],
                 oof_results: dict[str, dict[str, Any]],
                 training_tuple_sha256: str,
                 implementation_sha: str) -> dict[str, Any]:
    rbf_mean, _ = _pool_model_predictions(M4E2_CANDIDATE_SPECS[0], train_angles, train_truth, pool_angles)
    k24_mean, k24_std = _pool_model_predictions(M4E2_CANDIDATE_SPECS[1], train_angles, train_truth, pool_angles)
    k32_mean, _ = _pool_model_predictions(M4E2_CANDIDATE_SPECS[2], train_angles, train_truth, pool_angles)
    feature_distance = _distance_to_training(pool_angles, train_angles, "F1")
    _, pool_signatures, pool_orders, pool_margins = _labels_and_signature(pool_angles)
    train_signatures = set(_labels_and_signature(train_angles)[1])
    counts = {signature: pool_signatures.count(signature) for signature in set(pool_signatures)}
    rare_bonus = np.asarray([1.0 / np.sqrt(counts[s]) for s in pool_signatures])
    cutoff_bonus = 1.0 / (np.abs(pool_margins) + 0.005)
    bounds = quality["normalization_bounds"]
    std_scaled = np.column_stack([
        _minmax_with_bounds(k24_std[:, i], bounds, "native_std_k24") for i in range(3)
    ])
    disagreement = np.abs(k24_mean - k32_mean)
    disagreement_scaled = np.column_stack([
        _minmax_with_bounds(disagreement[:, i], bounds, "matern_k24_k32_disagreement")
        for i in range(3)
    ])
    rbf_disagreement = np.abs(rbf_mean - k24_mean)
    rbf_scaled = np.column_stack([
        _minmax_with_bounds(rbf_disagreement[:, i], bounds, "rbf_matern_disagreement")
        for i in range(3)
    ])
    distance_scaled = np.column_stack([
        _minmax_with_bounds(feature_distance, bounds, "nearest_training_distance") for _ in range(3)
    ])
    cutoff_scaled = _minmax_with_bounds(cutoff_bonus, bounds, "cutoff_topology_bonus")
    topology_scaled = _minmax_with_bounds(rare_bonus, bounds, "cutoff_topology_bonus")
    geometry_scaled = 0.5 * cutoff_scaled + 0.5 * topology_scaled
    geometry_scaled = np.column_stack((geometry_scaled,) * 3)
    ensemble = (M4E2_WEIGHTS["native_std"] * std_scaled +
                M4E2_WEIGHTS["matern_k24_k32_disagreement"] * disagreement_scaled +
                M4E2_WEIGHTS["rbf_matern_disagreement"] * rbf_scaled +
                M4E2_WEIGHTS["nearest_training_distance"] * distance_scaled +
                M4E2_WEIGHTS["cutoff_topology_bonus"] * geometry_scaled)
    score = np.max(ensemble, axis=1)
    # OOF worst-error/disagreement neighborhoods are defined before looking at
    # any candidate response; only train96 OOF quantities enter this mask.
    oof_k24 = oof_results["L2_local_matern_k24"]
    oof_k32 = oof_results["L2_local_matern_k32"]
    oof_hot_error = np.max(np.abs(oof_k24["prediction"] - train_truth), axis=1)
    oof_hot_disagreement = np.max(np.abs(oof_k24["prediction"] - oof_k32["prediction"]), axis=1)
    hotspot_indices = set(np.argsort(oof_hot_error + oof_hot_disagreement, kind="mergesort")[-20:])
    train_feature = angle_features(train_angles, "F1")
    pool_feature = angle_features(pool_angles, "F1")
    hotspot_feature = train_feature[np.asarray(sorted(hotspot_indices), dtype=np.int64)]
    hotspot_distance = np.min(np.linalg.norm(
        pool_feature[:, None, :] - hotspot_feature[None, :, :], axis=2), axis=1
    )
    hotspot_mask = hotspot_distance <= 0.12
    region = region_masks(pool_angles)
    cutoff_distance = np.abs(pool_margins)
    ordinary = region["ordinary_interior"] & (cutoff_distance > 0.02)
    unseen = np.asarray([signature not in train_signatures for signature in pool_signatures])
    allowed = np.ones(len(pool_angles), dtype=bool)
    train_tuples = {tuple(float(np.round(v, 12)) for v in row) for row in
                    np.column_stack((np.full(len(train_angles), 120.0), np.full(len(train_angles), 17.0), train_angles))}
    validation_set = {tuple(row) for row in validation_tuples}
    pool_tuples = [tuple(float(np.round(v, 12)) for v in row) for row in pool_data["tuples"]]
    allowed &= np.asarray([row not in train_tuples and row not in validation_set for row in pool_tuples])
    min_distance = 0.035
    selected: list[int] = []
    reasons: dict[int, list[str]] = {}
    rare_signatures: set[str] = set()

    def can_add(index: int) -> bool:
        return bool(allowed[index] and index not in selected and
                    all(float(np.linalg.norm(pool_feature[index] - pool_feature[other])) >= min_distance
                        for other in selected))

    def choose(count: int, predicate: Callable[[int], bool], reason: str) -> None:
        candidates = sorted((int(i) for i in range(len(pool_angles)) if predicate(int(i)) and can_add(int(i))),
                            key=lambda i: (-float(score[i]), i))
        if len(candidates) < count:
            raise RuntimeError(f"M4E2 plan cannot satisfy group {reason}: {len(candidates)}<{count}")
        for index in candidates[:count]:
            selected.append(index); reasons.setdefault(index, []).append(reason)

    # Preserve the explicit 2-point rare-topology requirement first, with two
    # different signatures and only response-blind mask geometry.
    for index in sorted((int(i) for i in range(len(pool_angles)) if unseen[i]),
                        key=lambda i: (-float(score[i]), i)):
        if pool_signatures[index] in rare_signatures or not can_add(index):
            continue
        selected.append(index); reasons.setdefault(index, []).append("rare_unseen_topology")
        rare_signatures.add(pool_signatures[index])
        if len(rare_signatures) == 2:
            break
    if len(rare_signatures) < 2:
        raise RuntimeError("M4E2 plan lacks two diverse unseen topology anchors")
    choose(6, lambda i: bool(hotspot_mask[i]), "matern_error_or_disagreement_hotspot")
    choose(3, lambda i: bool(region["high_azimuth"][i]), "high_azimuth_difficulty")
    choose(3, lambda i: bool(region["low_grazing"][i] or cutoff_distance[i] <= 0.02),
           "low_grazing_or_cutoff_side")
    choose(3, lambda i: bool(ordinary[i]), "ordinary_interior_hole")
    choose(16 - len(selected), lambda i: True, "space_filling_high_acquisition")
    if len(selected) != 16:
        raise RuntimeError("M4E2 plan did not produce exactly 16 points")
    plan_rows = []
    for index in selected:
        plan_rows.append({
            "candidate_index": int(index), "tuple": list(pool_tuples[index]),
            "angle": pool_angles[index].round(12).tolist(),
            "acquisition_score": float(score[index]),
            "acquisition_components": {
                "native_std_k24": std_scaled[index].tolist(),
                "matern_k24_k32_disagreement": disagreement_scaled[index].tolist(),
                "rbf_matern_disagreement": rbf_scaled[index].tolist(),
                "nearest_training_distance": distance_scaled[index].tolist(),
                "cutoff_topology_bonus": geometry_scaled[index].tolist(),
            },
            "nearest_training_distance": float(feature_distance[index]),
            "cutoff_order": int(pool_orders[index]),
            "signed_cutoff_margin": float(pool_margins[index]),
            "mask_signature": pool_signatures[index],
            "rare_unseen_topology": bool(unseen[index]),
            "selection_reasons": reasons.get(index, []),
        })
    point_tuples = [row["tuple"] for row in plan_rows]
    category_counts = {
        "hotspot": sum("matern_error_or_disagreement_hotspot" in r["selection_reasons"] for r in plan_rows),
        "high_azimuth": sum("high_azimuth_difficulty" in r["selection_reasons"] for r in plan_rows),
        "low_or_cutoff": sum("low_grazing_or_cutoff_side" in r["selection_reasons"] for r in plan_rows),
        "ordinary_interior": sum("ordinary_interior_hole" in r["selection_reasons"] for r in plan_rows),
        "rare_unseen_topology": sum(r["rare_unseen_topology"] for r in plan_rows),
    }
    pairwise = [float(np.linalg.norm(pool_feature[a] - pool_feature[b]))
                for pos, a in enumerate(selected) for b in selected[pos + 1:]]
    gates = {
        "acquisition_gate": bool(quality["gate"]),
        "exact_count_16": len(plan_rows) == 16,
        "training_validation_disjoint": bool(allowed[selected].all()),
        "tuple_hash_present": True,
        "hotspot_count_ge_6": category_counts["hotspot"] >= 6,
        "high_azimuth_count_ge_3": category_counts["high_azimuth"] >= 3,
        "low_or_cutoff_count_ge_3": category_counts["low_or_cutoff"] >= 3,
        "ordinary_interior_count_ge_3": category_counts["ordinary_interior"] >= 3,
        "rare_unseen_topology_count_ge_2": category_counts["rare_unseen_topology"] >= 2,
        "pairwise_normalized_distance_ge_0.035": bool(pairwise and min(pairwise) >= min_distance),
    }
    return {
        "schema_version": "task004.active-learning-round1-plan.v2",
        "dataset_id": "task004_angle_nominal_p5_ny4_train96_v2",
        "forward_solver_sha": "fdf961545f217d620e22800f2704ae9913a6d270",
        "model_identity": {"model_id": "S_PROD_FULL3D_STATIC_P5_H10_NY4",
                           "solver_route_id": "full3d_static_uniform_n1curl_p5_h10_ny4",
                           "mesh": [6, 4, 14], "mumps_icntl_14": 40,
                           "mpi": 2, "threads_per_rank": 1},
        "surrogate_training_code_sha": implementation_sha,
        "training_tuple_sha256": training_tuple_sha256,
        "validation_tuple_sha256": pool_data["validation_tuple_sha256"],
        "candidate_pool_tuple_sha256": pool_data["tuple_sha256"],
        "candidate_pool_count": int(len(pool_angles)), "point_count": len(plan_rows),
        "weights": M4E2_WEIGHTS, "minimum_normalized_distance": min_distance,
        "category_counts": category_counts, "pairwise_minimum_distance": min(pairwise),
        "gates": gates, "status": "ready_for_m4f" if all(gates.values()) else "controlled_stop",
        "fem_authorized_if_gates_pass": bool(all(gates.values())),
        "response_blind": True, "validation_response_accessed": False,
        "points": plan_rows,
        "point_tuple_sha256": _canonical(point_tuples),
    }


def run_m4e2(*, dataset_dir: Path, output_dir: Path, v2_windows: Path,
             stress_authority: Path, training_design: Path,
             validation_design: Path, candidate_pool: Path,
             implementation_sha: str) -> dict[str, Any]:
    """Run M4E2 and write diagnostics/plan, never a forward solver."""

    manifest = verify_immutable_package(dataset_dir)
    data = load_training_dataset(dataset_dir)
    angles = np.asarray(data["angles.npy"], dtype=np.float64)
    truth = np.asarray(data["aggregates.npy"], dtype=np.float64)[:, :3]
    design_data, _, training_tuples = _read_design(training_design)
    validation_data, validation_angles, validation_tuples = _read_design(validation_design)
    pool_data_raw, pool_angles, pool_tuples = _read_design(candidate_pool)
    pool_data = {"tuples": pool_tuples, "tuple_sha256": pool_data_raw["point_tuple_sha256"],
                 "validation_tuple_sha256": validation_data["point_tuple_sha256"]}
    if manifest.get("training_tuple_sha256") != design_data.get("point_tuple_sha256"):
        raise ValueError("train96/design tuple identity mismatch")
    if len(validation_angles) != 24 or len(pool_angles) != 4096:
        raise ValueError("M4E2 design counts do not match frozen contracts")
    v3_path = output_dir / "SUPPORTED_INTERPOLATION_WINDOWS_V3.json"
    v3 = freeze_supported_interpolation_windows_v3(
        angles=angles, v2_path=v2_windows, output=v3_path,
        dataset_id=manifest["dataset_id"], training_tuple_sha256=manifest["training_tuple_sha256"],
        stress_authority=stress_authority, implementation_sha=implementation_sha,
    )
    windows = {item["name"]: item for item in v3["windows"]}
    split = folds(angle_features(angles, F3_LOCAL_FEATURE), n_splits=5, seed=FOLD_SEED)
    split_id = fold_identity(angle_features(angles, F3_LOCAL_FEATURE), split, seed=FOLD_SEED)
    evaluated: dict[str, dict[str, Any]] = {}
    for spec in M4E2_CANDIDATE_SPECS:
        print("M4E2_CANDIDATE", spec["candidate"], flush=True)
        evaluated[spec["candidate"]] = _evaluate_oof_candidate(spec, angles, truth, split, windows)
    quality = _acquisition_quality(evaluated, angles, truth)
    quality["surrogate_training_code_sha"] = implementation_sha
    error_map = {
        "schema_version": "task004.m4e2.oof-error-map.v1",
        "dataset_id": manifest["dataset_id"], "training_tuple_sha256": manifest["training_tuple_sha256"],
        "surrogate_training_code_sha": implementation_sha,
        "fold_identity": split_id, "validation_target_accessed": False,
        "candidates": {},
    }
    for name, result in evaluated.items():
        error_map["candidates"][name] = {
            key: result[key] for key in ("candidate", "family", "neighbors", "feature",
                                         "metrics", "region_metrics", "uncertainty",
                                         "supported_windows", "aggregate_gate",
                                         "supported_window_gate", "composition_exact",
                                         "aggregate_qualified", "selection_score", "folds")
        }
        error_map["candidates"][name]["points"] = list(result["point_rows"].values())
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "M4E2_OOF_ERROR_MAP.json").write_text(
        json.dumps(error_map, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    (output_dir / "M4E2_ACQUISITION_QUALITY.json").write_text(
        json.dumps({key: value for key, value in quality.items()
                    if key != "acquisition_ensemble_oof"}, indent=2, sort_keys=True,
                   allow_nan=False) + "\n"
    )
    # Candidate-pool scoring is response-blind; it uses only train96 fits and
    # analytic geometry, never a candidate or validation response.
    plan = _plan_points(
        train_angles=angles, train_truth=truth, validation_tuples=validation_tuples,
        pool_data=pool_data, pool_angles=pool_angles, quality=quality,
        oof_results=evaluated,
        training_tuple_sha256=manifest["training_tuple_sha256"],
        implementation_sha=implementation_sha,
    )
    (output_dir / "ACTIVE_LEARNING_ROUND1_PLAN_V2.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    worst = sorted((row for result in evaluated.values() for row in result["point_rows"].values()),
                   key=lambda row: max(row["absolute_error"]), reverse=True)[:20]
    lines = ["# M4E2 worst OOF points", "", "The table is training-only; no candidate or validation response was read.", "",
             "| candidate | angle | max absolute error | nearest distance | cutoff order | margin |", "|---|---|---:|---:|---:|---:|"]
    for row in worst:
        lines.append(f"| n/a | {row['angle']} | {max(row['absolute_error']):.6g} | "
                     f"{row['nearest_fold_training_distance']:.6g} | {row['cutoff_order']} | "
                     f"{row['signed_cutoff_margin']:.6g} |")
    (output_dir / "M4E2_WORST_POINTS.md").write_text("\n".join(lines) + "\n")
    return {"windows": v3, "evaluated": evaluated, "quality": quality, "plan": plan}
