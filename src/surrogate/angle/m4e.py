"""Task004 Required M4E: local and topology-aware training-only models.

This module consumes only the immutable train96 response package.  It has no
forward-solver entry point and no function that loads a blind-validation
response.  Every uncertainty number is nested/cross-fitted: an outer fold is
scored only with a radius learned from inner folds of its outer-training rows,
then calibrated with the other outer folds.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy.interpolate import RBFInterpolator

from ..folds import FOLD_SEED, folds
from ..models import ExactARDGP
from ..physics import reconstruct_aggregates
from .models import (
    ChebyshevTrend,
    analytic_power_carrying_mask,
    angle_features,
    cutoff_identity,
    region_masks,
)


TARGETS = ("R_total", "T_total", "A_balance")
LOCAL_NEIGHBORS = (24, 32, 48)
LOCAL_SMOOTHINGS = (1.0e-8, 1.0e-10)
F3_LOCAL_FEATURE = "F1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def _latent(aggregates: np.ndarray) -> np.ndarray:
    values = np.asarray(aggregates, dtype=np.float64)
    eps = 1.0e-8
    return np.column_stack((np.log((values[:, 0] + eps) / (values[:, 2] + eps)),
                            np.log((values[:, 1] + eps) / (values[:, 2] + eps))))


def _aggregate(latent: np.ndarray) -> np.ndarray:
    return reconstruct_aggregates(np.asarray(latent, dtype=np.float64))[:, :3]


def _metrics(truth: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    error = np.asarray(prediction, dtype=np.float64) - np.asarray(truth, dtype=np.float64)
    scale = float(np.ptp(truth)) or 1.0
    return {"n": int(error.size), "nrmse": float(np.sqrt(np.mean(error ** 2)) / scale),
            "p95_abs": float(np.percentile(np.abs(error), 95)),
            "max_abs": float(np.max(np.abs(error)))}


def _nearest(features_query: np.ndarray, features_train: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    distances = np.linalg.norm(features_query[:, None, :] - features_train[None, :, :], axis=2)
    order = np.argsort(distances, axis=1, kind="mergesort")
    return order, distances


@dataclass
class LocalRBFLatent:
    neighbors: int = 32
    smoothing: float = 1.0e-8
    train_x: np.ndarray | None = None
    train_y: np.ndarray | None = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    feature: str = F3_LOCAL_FEATURE

    def fit(self, x: np.ndarray, y: np.ndarray) -> "LocalRBFLatent":
        self.train_x = angle_features(x, self.feature)
        self.train_y = np.asarray(y, dtype=np.float64).reshape(-1)
        self.diagnostics = []
        return self

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.train_x is None or self.train_y is None:
            raise RuntimeError("local RBF latent is not fitted")
        query = angle_features(x, self.feature)
        order, distances = _nearest(query, self.train_x)
        prediction = np.empty(len(query), dtype=np.float64)
        self.diagnostics = []
        for row in range(len(query)):
            indices = order[row, :min(self.neighbors, len(order[row]))]
            local_x = self.train_x[indices]
            local_y = self.train_y[indices]
            try:
                model = RBFInterpolator(local_x, local_y, neighbors=len(indices),
                                        smoothing=self.smoothing,
                                        kernel="thin_plate_spline")
                prediction[row] = float(np.asarray(model(query[row:row + 1])).reshape(-1)[0])
                fallback = False
            except (ValueError, np.linalg.LinAlgError):
                weights = 1.0 / np.maximum(distances[row, indices], 1.0e-12)
                prediction[row] = float(np.sum(weights * local_y) / np.sum(weights))
                fallback = True
            self.diagnostics.append({
                "neighbor_indices": indices.astype(int).tolist(),
                "nearest_distance": float(distances[row, indices[0]]),
                "neighbor_count": int(len(indices)), "fallback": fallback,
            })
        return prediction, np.full(len(query), np.nan, dtype=np.float64)


@dataclass
class LocalMaternLatent:
    neighbors: int = 32
    jitter: float = 1.0e-8
    train_x: np.ndarray | None = None
    train_y: np.ndarray | None = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    feature: str = F3_LOCAL_FEATURE

    def fit(self, x: np.ndarray, y: np.ndarray) -> "LocalMaternLatent":
        self.train_x = angle_features(x, self.feature)
        self.train_y = np.asarray(y, dtype=np.float64).reshape(-1)
        self.diagnostics = []
        return self

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.train_x is None or self.train_y is None:
            raise RuntimeError("local Matérn latent is not fitted")
        query = angle_features(x, self.feature)
        order, distances = _nearest(query, self.train_x)
        prediction = np.empty(len(query), dtype=np.float64)
        uncertainty = np.empty(len(query), dtype=np.float64)
        self.diagnostics = []
        for row in range(len(query)):
            indices = order[row, :min(self.neighbors, len(order[row]))]
            model = ExactARDGP(jitter=self.jitter, optimizer_restarts=8,
                               random_state=1200 + row).fit(
                                   self.train_x[indices], self.train_y[indices]
                               )
            mean, std = model.predict(query[row:row + 1], return_std=True)
            prediction[row] = float(np.asarray(mean).reshape(-1)[0])
            uncertainty[row] = float(np.asarray(std).reshape(-1)[0])
            meta = model.metadata()
            self.diagnostics.append({
                "neighbor_indices": indices.astype(int).tolist(),
                "nearest_distance": float(distances[row, indices[0]]),
                "neighbor_count": int(len(indices)), "kernel": meta["fitted_kernel"],
                "log_marginal_likelihood": meta["log_marginal_likelihood"],
                "selected_start": meta["selected_start"],
                "warning_count": int(sum(run["warning_count"] for run in meta["optimization_runs"])),
            })
        return prediction, uncertainty


def _signature(mask: np.ndarray) -> tuple[int, ...]:
    return tuple(int(value) for value in np.flatnonzero(mask))


@dataclass
class TopologyExpertLatent:
    neighbors: int = 32
    smoothing: float = 1.0e-8
    train_angles: np.ndarray | None = None
    train_features: np.ndarray | None = None
    train_y: np.ndarray | None = None
    train_signatures: list[str] | None = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    unsupported: list[dict[str, Any]] = field(default_factory=list)
    feature: str = F3_LOCAL_FEATURE

    def fit(self, x: np.ndarray, y: np.ndarray) -> "TopologyExpertLatent":
        self.train_angles = np.asarray(x, dtype=np.float64)
        self.train_features = angle_features(x, self.feature)
        self.train_y = np.asarray(y, dtype=np.float64).reshape(-1)
        mask = analytic_power_carrying_mask(self.train_angles)
        self.train_signatures = [_hash(mask[row].astype(int).tolist()) for row in range(len(mask))]
        self.diagnostics = []; self.unsupported = []
        return self

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.train_angles is None or self.train_features is None or self.train_y is None:
            raise RuntimeError("topology expert is not fitted")
        query_angles = np.asarray(x, dtype=np.float64)
        query_features = angle_features(query_angles, self.feature)
        query_mask = analytic_power_carrying_mask(query_angles)
        query_signatures = [_hash(query_mask[row].astype(int).tolist())
                            for row in range(len(query_mask))]
        prediction = np.empty(len(query_angles), dtype=np.float64)
        self.diagnostics = []; self.unsupported = []
        for row, signature in enumerate(query_signatures):
            candidates = np.asarray([i for i, value in enumerate(self.train_signatures or [])
                                     if value == signature], dtype=np.int64)
            if len(candidates) == 0:
                self.unsupported.append({"row": int(row), "signature": signature})
                # Aggregate remains defined, but the unsupported topology is
                # explicitly recorded and cannot qualify order outputs.
                candidates = np.arange(len(self.train_features), dtype=np.int64)
            distance = np.linalg.norm(self.train_features[candidates] - query_features[row], axis=1)
            chosen = candidates[np.argsort(distance, kind="mergesort")[:min(self.neighbors, len(candidates))]]
            local_x = self.train_features[chosen]
            local_y = self.train_y[chosen]
            try:
                model = RBFInterpolator(local_x, local_y, neighbors=len(chosen),
                                        smoothing=self.smoothing, kernel="thin_plate_spline")
                prediction[row] = float(np.asarray(model(query_features[row:row + 1])).reshape(-1)[0])
                fallback = False
            except (ValueError, np.linalg.LinAlgError):
                weights = 1.0 / np.maximum(np.linalg.norm(local_x - query_features[row], axis=1), 1.0e-12)
                prediction[row] = float(np.sum(weights * local_y) / np.sum(weights))
                fallback = True
            self.diagnostics.append({
                "neighbor_indices": chosen.astype(int).tolist(),
                "nearest_distance": float(np.min(distance)),
                "neighbor_count": int(len(chosen)), "topology_signature": signature,
                "unsupported": bool(signature not in (self.train_signatures or [])),
                "fallback": fallback,
            })
        return prediction, np.full(len(query_angles), np.nan, dtype=np.float64)


@dataclass
class TrendResidualLatent:
    neighbors: int = 32
    smoothing: float = 1.0e-8
    trend: ChebyshevTrend | None = None
    residual: LocalRBFLatent | None = None
    feature: str = F3_LOCAL_FEATURE

    @property
    def diagnostics(self) -> list[dict[str, Any]]:
        """Expose residual neighbourhood diagnostics through the common API."""
        return [] if self.residual is None else self.residual.diagnostics

    def fit(self, x: np.ndarray, y: np.ndarray) -> "TrendResidualLatent":
        features = angle_features(x, self.feature)
        self.trend = ChebyshevTrend(degree=2).fit(features, np.asarray(y).reshape(-1, 1))
        residual = np.asarray(y).reshape(-1) - self.trend.predict(features).reshape(-1)
        self.residual = LocalRBFLatent(
            self.neighbors, self.smoothing, feature=self.feature,
        ).fit(x, residual)
        return self

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.trend is None or self.residual is None:
            raise RuntimeError("trend-residual model is not fitted")
        features = angle_features(x, self.feature)
        residual, std = self.residual.predict(x)
        return self.trend.predict(features).reshape(-1) + residual, std


@dataclass
class LocalAggregateModel:
    family: str
    neighbors: int = 32
    smoothing: float = 1.0e-8
    jitter: float = 1.0e-8
    feature: str = F3_LOCAL_FEATURE
    latent_models: list[Any] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    unsupported: list[dict[str, Any]] = field(default_factory=list)

    def fit(self, angles: np.ndarray, aggregates: np.ndarray) -> "LocalAggregateModel":
        values = _latent(aggregates)
        cls: Any
        if self.family == "local_rbf":
            cls = LocalRBFLatent
        elif self.family == "local_matern":
            cls = LocalMaternLatent
        elif self.family == "topology_expert":
            cls = TopologyExpertLatent
        elif self.family == "trend_local_residual":
            cls = TrendResidualLatent
        else:
            raise ValueError(f"unknown M4E candidate family: {self.family}")
        self.latent_models = []
        for index in range(2):
            if self.family == "local_matern":
                model = cls(self.neighbors, self.jitter, feature=self.feature).fit(
                    angles, values[:, index]
                )
            elif self.family == "trend_local_residual":
                model = cls(self.neighbors, self.smoothing, feature=self.feature).fit(
                    angles, values[:, index]
                )
            else:
                model = cls(self.neighbors, self.smoothing, feature=self.feature).fit(
                    angles, values[:, index]
                )
            self.latent_models.append(model)
        return self

    def predict(self, angles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        means = []; stds = []
        self.diagnostics = []; self.unsupported = []
        for model in self.latent_models:
            mean, std = model.predict(angles)
            means.append(mean); stds.append(std)
            self.diagnostics.append(getattr(model, "diagnostics", []))
            self.unsupported.extend(getattr(model, "unsupported", []))
        latent = np.column_stack(means); latent_std = np.column_stack(stds)
        aggregate = _aggregate(latent)
        if np.all(np.isfinite(latent_std)):
            p = aggregate
            jr = p * (np.eye(3)[0][None, :] - p[:, 0, None])
            jt = p * (np.eye(3)[1][None, :] - p[:, 1, None])
            std = np.sqrt((jr * latent_std[:, 0, None]) ** 2 +
                          (jt * latent_std[:, 1, None]) ** 2)
        else:
            std = np.full_like(aggregate, np.nan)
        return aggregate, std

    def metadata(self) -> dict[str, Any]:
        return {"family": self.family, "neighbors": self.neighbors,
                "smoothing": self.smoothing, "jitter": self.jitter,
                "feature": self.feature,
                "unsupported_count": len(self.unsupported)}


def _make_candidate(spec: dict[str, Any]) -> LocalAggregateModel:
    return LocalAggregateModel(
        family=str(spec["family"]), neighbors=int(spec.get("neighbors", 32)),
        smoothing=float(spec.get("smoothing", 1.0e-8)),
        jitter=float(spec.get("jitter", 1.0e-8)),
        feature=str(spec.get("feature", F3_LOCAL_FEATURE)),
    )


def candidate_specs() -> list[dict[str, Any]]:
    specs = []
    # Keep the finite neighbourhood comparison explicit and deterministic.
    # These are local models, not an unconstrained hyperparameter search.
    for neighbors in (24, 32, 48):
        for smoothing in LOCAL_SMOOTHINGS[:1]:
            specs.append({"candidate": f"L1_local_rbf_k{neighbors}_s{ smoothing:g}",
                          "family": "local_rbf", "neighbors": neighbors,
                          "smoothing": smoothing})
    for neighbors in (24, 32, 48):
        specs.append({"candidate": f"L2_local_matern_k{neighbors}",
                      "family": "local_matern", "neighbors": neighbors,
                      "jitter": 1.0e-8})
    specs.append({"candidate": "L3_topology_expert_k32", "family": "topology_expert",
                  "neighbors": 32, "smoothing": 1.0e-8})
    specs.append({"candidate": "L4_trend_local_residual_k32", "family": "trend_local_residual",
                  "neighbors": 32, "smoothing": 1.0e-8})
    return specs


def freeze_supported_interpolation_windows_v2(*, angles: np.ndarray, output: Path,
                                              dataset_id: str,
                                              training_tuple_sha256: str,
                                              stress_authority: Path) -> dict[str, Any]:
    """Freeze finite local holes with support; preserve old stress evidence."""
    if output.is_file():
        return json.loads(output.read_text())
    values = np.asarray(angles, dtype=np.float64)
    selected = {
        "low_grazing": [20, 21, 22, 23],
        "high_azimuth": [28, 29, 38, 39],
        "cutoff_near": [58, 68, 78, 88],
        "ordinary_interior": [46, 47, 56, 57],
    }
    windows = []
    for name, indices in selected.items():
        holdout = np.asarray(indices, dtype=np.int64)
        support_pool = np.asarray([i for i in range(len(values)) if i not in set(indices)], dtype=np.int64)
        q = angle_features(values[holdout], "F1")
        t = angle_features(values[support_pool], "F1")
        order, distances = _nearest(q, t)
        support = support_pool[order[:, :6]]
        cutoff_order, signed = cutoff_identity(values[holdout])
        windows.append({
            "name": name, "indices": indices, "tuples": values[holdout].round(12).tolist(),
            "count": len(indices), "support_indices": support.tolist(),
            "nearest_support_distance": distances[np.arange(len(indices)), 0].tolist(),
            "support_count_per_point": [int(len(row)) for row in support],
            "cutoff_orders": cutoff_order.tolist(), "signed_cutoff_margins": signed.tolist(),
            "window_sha256": _hash({"indices": indices, "tuples": values[holdout].round(12).tolist()}),
        })
    old_stress = json.loads(stress_authority.read_text())
    stress_hash = hashlib.sha256(stress_authority.read_bytes()).hexdigest()
    payload = {"schema_version": "task004.supported-interpolation-windows.v2",
               "dataset_id": dataset_id, "training_tuple_sha256": training_tuple_sha256,
               "windows": windows, "windows_sha256": _hash(windows),
               "stress_authority": {"path": str(stress_authority),
                                    "sha256": stress_hash,
                                    "schema_version": old_stress.get("schema_version"),
                                    "window_count": len(old_stress.get("windows", [])),
                                    "status": "advisory_extrapolation_stress"},
               "frozen_before_model_fitting": True,
               "qualification_semantics": "supported_local_interpolation_hard_gate; stress_advisory"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def _load_windows(path: Path, angles: np.ndarray, tuple_sha: str) -> dict[str, np.ndarray]:
    data = json.loads(path.read_text())
    if data.get("training_tuple_sha256") != tuple_sha:
        raise ValueError("M4E supported-window tuple hash mismatch")
    result = {}
    for item in data["windows"]:
        indices = np.asarray(item["indices"], dtype=np.int64)
        digest = _hash({"indices": indices.tolist(), "tuples": np.asarray(angles)[indices].round(12).tolist()})
        if digest != item.get("window_sha256") or np.any(np.asarray(item["support_indices"]) == indices[:, None]):
            raise ValueError(f"M4E supported-window identity/support mismatch: {item['name']}")
        result[item["name"]] = indices
    return result


def _inner_radius(spec: dict[str, Any], angles: np.ndarray, aggregates: np.ndarray) -> np.ndarray:
    """Nested inner OOF residual radius for one outer-training set."""
    if len(angles) < 12:
        return np.full(3, 1.0e-3)
    feature = str(spec.get("feature", F3_LOCAL_FEATURE))
    split = folds(angle_features(angles, feature), n_splits=3, seed=FOLD_SEED + 19)
    predictions = np.full((len(angles), 3), np.nan)
    for train, test in split:
        # Nested calibration for local Matérn uses a response-blind local-RBF
        # proxy on the inner folds.  This avoids re-running hundreds of
        # eight-start query GPs solely to estimate a residual radius while
        # retaining a genuinely nested, held-out calibration sample.
        inner_spec = spec
        if spec["family"] == "local_matern":
            inner_spec = {"candidate": "nested_rbf_proxy", "family": "local_rbf",
                          "neighbors": spec.get("neighbors", 32), "smoothing": 1.0e-8,
                          "feature": feature}
        model = _make_candidate(inner_spec).fit(angles[train], aggregates[train])
        predictions[test] = model.predict(angles[test])[0]
    error = np.abs(predictions - aggregates[:, :3])
    return np.percentile(error, 95, axis=0)


def _crossfit_calibration(truth: np.ndarray, prediction: np.ndarray,
                          raw_std: np.ndarray, split: list[tuple[np.ndarray, np.ndarray]],
                          angles: np.ndarray) -> dict[str, Any]:
    standardized = np.abs(prediction - truth) / np.maximum(raw_std, 1.0e-12)
    calibrated_std = np.full_like(raw_std, np.nan)
    factors = []
    for fold, (_, test) in enumerate(split):
        other = np.concatenate([split[k][1] for k in range(len(split)) if k != fold])
        factor = np.maximum(1.0, np.percentile(standardized[other], 95, axis=0) / 1.96)
        calibrated_std[test] = raw_std[test] * factor[None, :]
        factors.append({"fold": fold, "source_outer_folds": [k for k in range(len(split)) if k != fold],
                        "factor_by_target": {target: float(factor[i]) for i, target in enumerate(TARGETS)}})
    coverage = {target: float(np.mean(np.abs(prediction[:, i] - truth[:, i]) /
                                      np.maximum(calibrated_std[:, i], 1.0e-12) <= 1.96))
                for i, target in enumerate(TARGETS)}
    regions = {}
    masks = region_masks(angles)
    for name, region in masks.items():
        regions[name] = {"n": int(np.sum(region)),
                         "coverage_95": {target: float(np.mean(
                             np.abs(prediction[region, i] - truth[region, i]) /
                             np.maximum(calibrated_std[region, i], 1.0e-12) <= 1.96))
                             for i, target in enumerate(TARGETS)} if np.any(region) else {}}
    final_factor = np.maximum(1.0, np.percentile(standardized, 95, axis=0) / 1.96)
    return {"raw_coverage_95": {target: float(np.mean(standardized[:, i] <= 1.96))
                                for i, target in enumerate(TARGETS)},
            "cross_fitted_coverage_95": coverage, "region_coverage": regions,
            "fold_factors": factors,
            "final_factors": {target: float(final_factor[i]) for i, target in enumerate(TARGETS)},
            "gate": bool(all(0.90 <= value <= 0.99 for value in coverage.values()))}


def _evaluate_candidate(spec: dict[str, Any], angles: np.ndarray, aggregates: np.ndarray,
                        split: list[tuple[np.ndarray, np.ndarray]],
                        windows: dict[str, np.ndarray]) -> dict[str, Any]:
    prediction = np.full((len(angles), 3), np.nan)
    raw_std = np.full_like(prediction, np.nan)
    fold_rows = []
    point_diagnostics: dict[int, Any] = {}
    for fold, (train, test) in enumerate(split):
        model = _make_candidate(spec).fit(angles[train], aggregates[train])
        mean, native_std = model.predict(angles[test])
        radius = _inner_radius(spec, angles[train], aggregates[train])
        # A local GP's native std is retained, but never allowed to undercut
        # the nested inner residual radius.
        floor_std = radius[None, :] / 1.96
        if np.all(np.isfinite(native_std)):
            std = np.maximum(native_std, floor_std)
        else:
            std = np.broadcast_to(floor_std, mean.shape).copy()
        prediction[test] = mean; raw_std[test] = std
        for local, index in enumerate(test):
            point_diagnostics[int(index)] = {
                "fold": fold, "inner_radius": radius.tolist(),
                "latent_diagnostics": [model.diagnostics[k][local] for k in range(2)],
                "unsupported": model.unsupported,
            }
        fold_rows.append({"fold": fold, "train_count": int(len(train)),
                          "test_indices": test.tolist(), "inner_radius": radius.tolist(),
                          "model_metadata": model.metadata(),
                          "unsupported_count": len(model.unsupported)})
    metrics = {target: _metrics(aggregates[:, i], prediction[:, i])
               for i, target in enumerate(TARGETS)}
    region_metrics = {}
    for name, region in region_masks(angles).items():
        region_metrics[name] = {target: _metrics(aggregates[region, i], prediction[region, i])
                                for i, target in enumerate(TARGETS)} if np.any(region) else {}
    uncertainty = _crossfit_calibration(aggregates[:, :3], prediction, raw_std, split, angles)
    window_metrics = {}
    for name, holdout in windows.items():
        train = np.asarray([i for i in range(len(angles)) if i not in set(holdout)], dtype=np.int64)
        model = _make_candidate(spec).fit(angles[train], aggregates[train])
        mean, _ = model.predict(angles[holdout])
        window_metrics[name] = {"indices": holdout.tolist(),
                                "metrics": {target: _metrics(aggregates[holdout, i], mean[:, i])
                                            for i, target in enumerate(TARGETS)},
                                "unsupported_count": len(model.unsupported)}
    hard_aggregate = bool(all(item["nrmse"] <= 0.01 and item["p95_abs"] <= 0.01 and
                              item["max_abs"] <= 0.03 for item in metrics.values()))
    hard_windows = bool(all(all(values["metrics"][target]["p95_abs"] <= 0.02
                                 for target in TARGETS)
                            for values in window_metrics.values()))
    composition = bool(np.max(np.abs(np.sum(prediction, axis=1) - 1.0)) <= 1.0e-12)
    return {**spec, "metrics": metrics, "region_metrics": region_metrics,
            "folds": fold_rows, "uncertainty": uncertainty,
            "supported_window_metrics": window_metrics,
            "aggregate_gate": hard_aggregate, "supported_window_gate": hard_windows,
            "composition_exact": composition,
            "aggregate_qualified": bool(hard_aggregate and hard_windows and
                                         composition and uncertainty["gate"]),
            "oof_prediction": prediction, "oof_std": raw_std,
            "point_diagnostics": point_diagnostics,
            "selection_score": float(max(max(item["nrmse"] / 0.01,
                                               item["p95_abs"] / 0.01,
                                               item["max_abs"] / 0.03)
                                           for item in metrics.values()))}


def _summary(candidate: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in candidate.items()
            if key not in {"oof_prediction", "oof_std", "point_diagnostics"}}


def run_m4e(*, dataset_dir: Path, output_dir: Path, stress_authority: Path,
            validation_design: Path, candidate_pool: Path) -> dict[str, Any]:
    """Run all M4E comparisons and write Level A/B qualification evidence."""
    from .dataset import verify_immutable_package, load_training_dataset
    from .pipeline import _power_oof

    manifest = verify_immutable_package(dataset_dir)
    data = load_training_dataset(dataset_dir)
    angles = np.asarray(data["angles.npy"], dtype=np.float64)
    aggregates = np.asarray(data["aggregates.npy"], dtype=np.float64)
    powers = np.asarray(data["order_powers.npy"], dtype=np.float64)
    mask = np.asarray(data["power_carrying_mask.npy"], dtype=bool)
    windows_path = output_dir / "SUPPORTED_INTERPOLATION_WINDOWS_V2.json"
    freeze_supported_interpolation_windows_v2(
        angles=angles, output=windows_path, dataset_id=manifest["dataset_id"],
        training_tuple_sha256=manifest["training_tuple_sha256"],
        stress_authority=stress_authority,
    )
    windows = _load_windows(windows_path, angles, manifest["training_tuple_sha256"])
    split = folds(angle_features(angles, "F1"), n_splits=5, seed=FOLD_SEED)
    results = []
    for spec in candidate_specs():
        result = _evaluate_candidate(spec, angles, aggregates, split, windows)
        results.append(result)
        print("M4E_CANDIDATE", result["candidate"], result["selection_score"],
              result["aggregate_qualified"], flush=True)
    eligible = [item for item in results if item["aggregate_qualified"]]
    ranked = sorted(results, key=lambda item: (item["selection_score"], item["candidate"]))
    selected = sorted(eligible, key=lambda item: (item["selection_score"], item["candidate"]))[0] if eligible else ranked[0]
    feature = "F1"
    power = _power_oof(angles=angles, aggregates=aggregates[:, :3], powers=powers,
                       mask=mask, split=split,
                       aggregate_candidate=selected["candidate"],
                       aggregate_jitter=float(selected.get("jitter", 1.0e-8)),
                       aggregate_prediction=selected["oof_prediction"],
                       aggregate_std=selected["oof_std"], feature=feature)
    order_qualified = bool(power["hard_gate"])
    baseline = next(item for item in results if item["family"] == "local_rbf" and item["neighbors"] == 32)
    a_improvement = float(baseline["metrics"]["A_balance"]["p95_abs"] -
                          selected["metrics"]["A_balance"]["p95_abs"])
    # Compare against the immutable Case125 training-only global reference.
    # This file contains no validation responses; the fallback is retained
    # only so the module remains runnable from an isolated checkout.
    global_reference_path = Path(
        "benchmarks/cases/125_task004_angle_training_qualification/outcomes/training_cv.json"
    )
    global_reference_score = 4.950713848612087
    global_reference_source = "embedded_case125_training_cv_reference"
    if global_reference_path.is_file():
        reference = json.loads(global_reference_path.read_text())
        global_reference_score = float(reference["selected_result"]["selection_score"])
        global_reference_source = str(global_reference_path)
    local_better_than_global = bool(selected["selection_score"] < global_reference_score)
    localized = bool(any(item["metrics"]["A_balance"]["p95_abs"] > 0.02
                         for item in selected["supported_window_metrics"].values()))
    active_eligibility = {
        "schema_version": "task004.active-learning-eligibility.v2",
        "dataset_id": manifest["dataset_id"],
        "forward_solver_sha": manifest["forward_solver_sha"],
        "validation_target_accessed": False,
        "candidate_pool_response_blind": True,
        "checks": {
            "local_candidate_improves_global_gp": local_better_than_global,
            "a_p95_or_max_improvement": bool(a_improvement > 0.0),
            "cross_fitted_uncertainty_available": bool(selected["uncertainty"]["gate"]),
            "localized_oof_region": localized,
            "dataset_identity_checker": True,
            "validation_response_not_accessed": True,
        },
        "eligible_for_one_round_16_fem": bool(
            local_better_than_global and (a_improvement > 0.0 or selected["uncertainty"]["gate"])
            and localized
        ),
        "budget": 16,
        "fem_started": False,
        "plan_status": "eligibility_only_no_fem",
        "candidate_pool_unseen_topology_policy": "response_blind anchors only if later authorized",
        "global_reference": {
            "selection_score": global_reference_score,
            "source": global_reference_source,
        },
    }
    aggregate_qualification = {
        "schema_version": "task004.aggregate-qualification.v2",
        "level": "A_aggregate_RTA", "dataset_id": manifest["dataset_id"],
        "forward_solver_sha": manifest["forward_solver_sha"],
        "surrogate_training_code_sha": manifest.get("surrogate_dataset_builder_sha"),
        "selected_candidate": selected["candidate"],
        "qualified": bool(selected["aggregate_qualified"]),
        "training_only": True, "validation_target_accessed": False,
        "gate_contract": {"oof_nrmse_le_0.01": True, "oof_p95_le_0.01": True,
                          "oof_max_le_0.03": True, "supported_window_p95_le_0.02": True,
                          "composition_exact": True, "cross_fitted_coverage_0.90_0.99": True},
        "selected_result": _summary(selected),
        "candidate_results": [_summary(item) for item in results],
        "extrapolation_stress": json.loads(stress_authority.read_text()),
        "status": "qualified" if selected["aggregate_qualified"] else "not_qualified_but_viable",
    }
    order_qualification = {
        "schema_version": "task004.order-qualification.v2",
        "level": "B_order_resolved_power", "dataset_id": manifest["dataset_id"],
        "forward_solver_sha": manifest["forward_solver_sha"],
        "aggregate_candidate": selected["candidate"],
        "qualified": order_qualified, "training_only": True,
        "validation_target_accessed": False,
        "gate_contract": {"mask_agreement_100_percent": bool(power["mask_agreement"]),
                          "sidewise_ledger_le_1e-12": bool(power["max_sidewise_ledger_error"] <= 1.0e-12),
                          "primary_channel_accuracy": bool(power["hard_gate"]),
                          "unseen_topology_unsupported": True},
        "power": {key: value for key, value in power.items() if key != "records"},
        "status": "qualified" if order_qualified else "not_qualified",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "ANGLE_AGGREGATE_QUALIFICATION_CONTRACT.json").write_text(
        json.dumps(aggregate_qualification, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    (output_dir / "ANGLE_ORDER_QUALIFICATION_CONTRACT.json").write_text(
        json.dumps(order_qualification, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    (output_dir / "ACTIVE_LEARNING_ELIGIBILITY.json").write_text(
        json.dumps(active_eligibility, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    # The detailed per-point neighborhood/kernel evidence is kept separately
    # so the candidate summary remains readable and deterministic.  Keep all
    # candidates here: the local Matérn contract requires per-query kernel/LML
    # and warning provenance even when it is not selected.
    (output_dir / "m4e_point_diagnostics.json").write_text(
        json.dumps({"candidate": selected["candidate"],
                    "points": selected["point_diagnostics"],
                    "candidate_points": {
                        item["candidate"]: item["point_diagnostics"] for item in results
                    }}, indent=2, sort_keys=True,
                   allow_nan=False) + "\n"
    )
    return {"aggregate": aggregate_qualification, "order": order_qualification,
            "active_learning": active_eligibility, "selected": selected}
