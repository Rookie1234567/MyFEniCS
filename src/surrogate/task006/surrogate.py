"""Finite Task006 surrogate candidates and grouped training-only qualification."""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
from scipy.optimize import minimize

from ..models import ExactARDGP, OrthogonalPCE, TrendResidualGP
from .dataset import EPSILON, load_dataset


N1_FLOOR = 1.0e-4
N2_FLOOR = 5.0e-4
FEATURE_MIN = np.asarray([115.0, 16.0])
FEATURE_MAX = np.asarray([125.0, 18.0])


def scale_geometry(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    return 2.0 * (values - FEATURE_MIN) / (FEATURE_MAX - FEATURE_MIN) - 1.0


def noise_sigma(values: np.ndarray, scenario: str = "N1") -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    if scenario == "N1":
        return np.sqrt((0.01 * np.abs(values)) ** 2 + N1_FLOOR ** 2)
    if scenario == "N2":
        return np.sqrt((0.02 * np.abs(values)) ** 2 + N2_FLOOR ** 2)
    raise ValueError("noise scenario must be N1 or N2")


def fold_indices(n: int = 37, n_splits: int = 5) -> list[tuple[np.ndarray, np.ndarray]]:
    ids = np.arange(n, dtype=np.int64)
    result = []
    for fold in range(n_splits):
        test = ids[ids % n_splits == fold]
        train = ids[ids % n_splits != fold]
        result.append((train, test))
    return result


class FitModel:
    def fit(self, x: np.ndarray, y: np.ndarray) -> "FitModel":
        raise NotImplementedError

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError

    def metadata(self) -> dict[str, Any]:
        return {}


@dataclass
class PolynomialModel(FitModel):
    degree: int
    ridge: float = 1.0e-10
    coefficients: np.ndarray | None = None
    condition_number: float | None = None
    residual_sigma: float = 1.0e-6
    _indices: list[tuple[int, ...]] | None = None

    def _basis(self, x: np.ndarray) -> np.ndarray:
        values = np.asarray(x, dtype=np.float64)
        if self._indices is None:
            self._indices = [powers for powers in itertools.product(range(self.degree + 1), repeat=values.shape[1])
                             if sum(powers) <= self.degree]
        columns = []
        for powers in self._indices:
            term = np.ones(len(values), dtype=np.float64)
            for axis, order in enumerate(powers):
                coeff = np.zeros(order + 1); coeff[-1] = 1.0
                term *= np.polynomial.legendre.legval(values[:, axis], coeff)
            columns.append(term)
        return np.column_stack(columns)

    def fit(self, x: np.ndarray, y: np.ndarray) -> "PolynomialModel":
        design = self._basis(x)
        lhs = design.T @ design + self.ridge * np.eye(design.shape[1])
        self.condition_number = float(np.linalg.cond(lhs))
        self.coefficients = np.linalg.solve(lhs, design.T @ np.asarray(y, dtype=np.float64))
        residual = np.asarray(y, dtype=np.float64) - design @ self.coefficients
        self.residual_sigma = float(max(np.std(residual, ddof=1) if residual.size > 1 else 0.0, 1.0e-8))
        return self

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.coefficients is None:
            raise RuntimeError("polynomial model not fitted")
        values = self._basis(x) @ self.coefficients
        return values, np.full(len(np.asarray(x)), self.residual_sigma, dtype=np.float64)

    def metadata(self) -> dict[str, Any]:
        return {"family": "legendre_total_degree", "degree": self.degree,
                "ridge": self.ridge, "condition_number": self.condition_number,
                "residual_sigma": self.residual_sigma,
                "term_count": len(self._indices or [])}


@dataclass
class LocalRBFModel(FitModel):
    neighbors: int = 8
    smoothing: float = 1.0e-10
    x_train: np.ndarray | None = None
    y_train: np.ndarray | None = None
    residual_sigma: float = 1.0e-6

    def fit(self, x: np.ndarray, y: np.ndarray) -> "LocalRBFModel":
        self.x_train = np.asarray(x, dtype=np.float64)
        self.y_train = np.asarray(y, dtype=np.float64)
        pred, _ = self.predict(self.x_train)
        residual = self.y_train - pred
        self.residual_sigma = float(max(np.std(residual, ddof=1) if residual.size > 1 else 0.0, 1.0e-8))
        return self

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.x_train is None or self.y_train is None:
            raise RuntimeError("RBF model not fitted")
        query = np.asarray(x, dtype=np.float64)
        output = np.empty(len(query), dtype=np.float64)
        for i, row in enumerate(query):
            distance = np.linalg.norm(self.x_train - row, axis=1)
            k = min(self.neighbors, len(distance))
            order = np.argsort(distance, kind="mergesort")[:k]
            local = distance[order]
            bandwidth = max(float(local[-1]), 1.0e-6)
            weights = np.exp(-(local / bandwidth) ** 2) + self.smoothing
            weights /= np.sum(weights)
            output[i] = float(np.dot(weights, self.y_train[order]))
        return output, np.full(len(query), self.residual_sigma, dtype=np.float64)

    def metadata(self) -> dict[str, Any]:
        return {"family": "local_gaussian_rbf", "neighbors": self.neighbors,
                "smoothing": self.smoothing, "residual_sigma": self.residual_sigma}


class ExactModel(FitModel):
    def __init__(self, *, seed: int):
        self.model = ExactARDGP(jitter=1.0e-10, optimizer_restarts=8,
                                random_state=int(seed), normalize_y=True)

    def fit(self, x: np.ndarray, y: np.ndarray) -> "ExactModel":
        self.model.fit(x, y)
        return self

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        mean, std = self.model.predict(x, return_std=True)
        return np.asarray(mean), np.asarray(std)

    def metadata(self) -> dict[str, Any]:
        return self.model.metadata()


class TrendModel(FitModel):
    def __init__(self, *, seed: int):
        self.model = TrendResidualGP(jitter=1.0e-10, optimizer_restarts=8,
                                     random_state=int(seed), trend_kind="legendre", trend_degree=2)

    def fit(self, x: np.ndarray, y: np.ndarray) -> "TrendModel":
        self.model.fit(x, y)
        return self

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        mean, std = self.model.predict(x, return_std=True)
        return np.asarray(mean), np.asarray(std)

    def metadata(self) -> dict[str, Any]:
        return self.model.metadata()


def make_model(candidate: str, *, seed: int) -> FitModel:
    if candidate.startswith("legendre_"):
        return PolynomialModel(int(candidate.split("_")[1]))
    if candidate == "local_rbf_k8":
        return LocalRBFModel(neighbors=8)
    if candidate == "matern52_ard_exact_gp":
        return ExactModel(seed=seed)
    if candidate == "degree2_trend_plus_matern52_residual":
        return TrendModel(seed=seed)
    raise ValueError(f"unknown candidate {candidate}")


def _fit_block(candidate: str, x_train: np.ndarray, y_train: np.ndarray,
               x_query: np.ndarray, *, seed: int) -> tuple[np.ndarray, np.ndarray, dict[str, Any], FitModel]:
    model = make_model(candidate, seed=seed)
    model.fit(x_train, y_train)
    mean, std = model.predict(x_query)
    return mean, np.maximum(np.asarray(std, dtype=np.float64), 1.0e-10), model.metadata(), model


def sigmoid(logit: np.ndarray) -> np.ndarray:
    values = np.clip(np.asarray(logit, dtype=np.float64), -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-values))


def _fit_contract(candidate: str, geometry: np.ndarray, aggregate_latent: np.ndarray,
                  side_totals: np.ndarray, fractions: np.ndarray,
                  train: np.ndarray, query: np.ndarray, *, seed: int) -> dict[str, Any]:
    x_train = scale_geometry(geometry[train]); x_query = scale_geometry(query)
    aggregate_mean = np.empty((len(query), 3, 2)); aggregate_std = np.empty_like(aggregate_mean)
    side_mean = np.empty((len(query), 3, 2)); side_std = np.empty_like(side_mean)
    frac_mean = np.empty((len(query), 3, 2)); frac_std = np.empty_like(frac_mean)
    fits: list[dict[str, Any]] = []
    aggregate_models: list[FitModel] = []
    side_models: list[FitModel] = []
    fraction_models: list[FitModel] = []
    for angle in range(3):
        for target in range(2):
            mean, std, meta, model = _fit_block(candidate, x_train, aggregate_latent[train, angle, target], x_query, seed=seed + angle * 11 + target)
            aggregate_mean[:, angle, target] = mean; aggregate_std[:, angle, target] = std
            aggregate_models.append(model)
            fits.append({"contract": "S0", "angle_index": angle, "target_index": target, "metadata": meta})
            mean, std, meta, model = _fit_block(candidate, x_train, side_totals[train, angle, target], x_query, seed=seed + 100 + angle * 11 + target)
            side_mean[:, angle, target] = np.maximum(mean, 0.0); side_std[:, angle, target] = std
            side_models.append(model)
            fits.append({"contract": "S1_side_total", "angle_index": angle, "target_index": target, "metadata": meta})
            logits = np.log((fractions[train, angle, target, 0] + EPSILON) / (fractions[train, angle, target, 1] + EPSILON))
            mean, std, meta, model = _fit_block(candidate, x_train, logits, x_query, seed=seed + 200 + angle * 11 + target)
            frac_mean[:, angle, target] = sigmoid(mean); frac_std[:, angle, target] = np.maximum(std * frac_mean[:, angle, target] * (1.0 - frac_mean[:, angle, target]), 1.0e-10)
            fraction_models.append(model)
            fits.append({"contract": "S1_fraction_logit", "angle_index": angle, "target_index": target, "metadata": meta})
    logits = np.concatenate([aggregate_mean, np.zeros((len(query), 3, 1))], axis=2)
    logits -= np.max(logits, axis=2, keepdims=True)
    weights = np.exp(logits); weights /= np.sum(weights, axis=2, keepdims=True)
    aggregate_prediction = weights
    # A conservative delta-method uncertainty for the composition softmax.
    aggregate_prediction_std = np.maximum(np.max(aggregate_std, axis=2, keepdims=True) * np.ones_like(aggregate_prediction), 1.0e-10)
    selected_prediction = side_mean * frac_mean
    other_prediction = side_mean * (1.0 - frac_mean)
    selected_std = np.sqrt((frac_mean * side_std) ** 2 + (side_mean * frac_std) ** 2)
    other_std = np.sqrt(((1.0 - frac_mean) * side_std) ** 2 + (side_mean * frac_std) ** 2)
    return {
        "aggregate_prediction": aggregate_prediction,
        "aggregate_std": aggregate_prediction_std,
        "side_prediction": side_mean, "side_std": side_std,
        "fraction_prediction": frac_mean, "fraction_std": frac_std,
        "selected_prediction": selected_prediction, "selected_std": selected_std,
        "other_prediction": other_prediction, "other_std": other_std,
        "fits": fits,
        "_models": {"aggregate": aggregate_models, "side": side_models, "fraction": fraction_models},
    }


def _predict_fitted_contract(models: dict[str, list[FitModel]], query: np.ndarray) -> dict[str, np.ndarray]:
    """Predict a contract from already fitted scalar models (used in recovery)."""

    x_query = scale_geometry(query)
    n = len(query)
    aggregate_mean = np.empty((n, 3, 2)); aggregate_std = np.empty_like(aggregate_mean)
    side_mean = np.empty((n, 3, 2)); side_std = np.empty_like(side_mean)
    frac_mean = np.empty((n, 3, 2)); frac_std = np.empty_like(frac_mean)
    for angle in range(3):
        for target in range(2):
            index = angle * 2 + target
            mean, std = models["aggregate"][index].predict(x_query)
            aggregate_mean[:, angle, target] = mean; aggregate_std[:, angle, target] = np.maximum(std, 1.0e-10)
            mean, std = models["side"][index].predict(x_query)
            side_mean[:, angle, target] = np.maximum(mean, 0.0); side_std[:, angle, target] = np.maximum(std, 1.0e-10)
            mean, std = models["fraction"][index].predict(x_query)
            frac_mean[:, angle, target] = sigmoid(mean); frac_std[:, angle, target] = np.maximum(std * frac_mean[:, angle, target] * (1.0 - frac_mean[:, angle, target]), 1.0e-10)
    logits = np.concatenate([aggregate_mean, np.zeros((n, 3, 1))], axis=2)
    logits -= np.max(logits, axis=2, keepdims=True)
    weights = np.exp(logits); weights /= np.sum(weights, axis=2, keepdims=True)
    selected_prediction = side_mean * frac_mean
    selected_std = np.sqrt((frac_mean * side_std) ** 2 + (side_mean * frac_std) ** 2)
    return {"aggregate_prediction": weights, "selected_prediction": selected_prediction, "selected_std": selected_std}


def _target_metrics(truth: np.ndarray, prediction: np.ndarray, std: np.ndarray,
                    *, normalized: bool = False) -> dict[str, Any]:
    error = np.asarray(prediction) - np.asarray(truth)
    scale = float(np.ptp(truth)) or 1.0
    sigma = noise_sigma(truth, "N1")
    normalized_error = np.abs(error) / sigma
    half_width = 1.96 * np.maximum(np.asarray(std), 1.0e-10)
    return {
        "n": int(error.size), "nrmse": float(np.sqrt(np.mean(error ** 2)) / scale),
        "p95_abs": float(np.percentile(np.abs(error), 95)), "max_abs": float(np.max(np.abs(error))),
        "p95_normalized_N1": float(np.percentile(normalized_error, 95)),
        "max_normalized_N1": float(np.max(normalized_error)),
        "coverage_95": float(np.mean(np.abs(error) <= half_width)),
        "p95_half_width": float(np.percentile(half_width, 95)),
        "p95_N1_sigma": float(np.percentile(sigma, 95)),
        "finite_positive_width": bool(np.all(np.isfinite(half_width)) and np.all(half_width > 0.0)),
        "normalized": normalized,
    }


def _regions(geometry: np.ndarray) -> list[str]:
    return ["boundary" if h in (115.0, 125.0) or w in (16.0, 18.0) else "interior" for h, w in geometry]


def _nearest_distance(geometry: np.ndarray, train: np.ndarray) -> np.ndarray:
    values = scale_geometry(geometry); source = scale_geometry(train)
    return np.asarray([float(np.min(np.linalg.norm(source - row, axis=1))) for row in values])


def _score(result: dict[str, Any]) -> float:
    values = []
    for target in result["s0_metrics"].values():
        values.extend([target["nrmse"] / 0.01, target["p95_abs"] / 0.005, target["max_abs"] / 0.015])
    for target in result["s1_metrics"].values():
        values.extend([target["nrmse"] / 0.02, target["p95_normalized_N1"] / 0.75, target["max_normalized_N1"] / 2.0])
    values.extend([1.0 / max(result["uncertainty"]["minimum_coverage"], 1.0e-12), result["uncertainty"]["p95_width_over_N1_sigma"]])
    return float(max(values))


def run_training_cv(*, dataset_root: Path, outcomes: Path) -> dict[str, Any]:
    data = load_dataset(dataset_root)
    geometry = np.asarray(data["geometries"], dtype=np.float64)
    aggregates = np.asarray(data["aggregates"][:, :, :3], dtype=np.float64)
    latent = np.asarray(data["aggregate_latent"], dtype=np.float64)
    side = np.asarray(data["s1_side_totals"], dtype=np.float64)
    fractions = np.asarray(data["s1_fractions"], dtype=np.float64)
    folds = fold_indices(len(geometry), 5)
    regions = _regions(geometry)
    candidates = ["legendre_2", "legendre_3", "legendre_4", "local_rbf_k8", "matern52_ard_exact_gp", "degree2_trend_plus_matern52_residual"]
    comparison: dict[str, Any] = {}
    all_oof: list[dict[str, Any]] = []
    candidate_runs: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        s0_pred = np.full_like(aggregates, np.nan); s0_std = np.full_like(aggregates, np.nan)
        s1_pred = np.full((len(geometry), 3, 2), np.nan); s1_std = np.full_like(s1_pred, np.nan)
        s1_truth = np.asarray(data["s1_selected_powers"], dtype=np.float64)
        fold_row = np.full(len(geometry), -1, dtype=np.int64)
        fit_records: list[dict[str, Any]] = []
        for fold, (train, test) in enumerate(folds):
            fold_row[test] = fold
            block = _fit_contract(candidate, geometry, latent, side, fractions, train, geometry[test], seed=700 + fold * 97)
            s0_pred[test] = block["aggregate_prediction"]; s0_std[test] = block["aggregate_std"]
            s1_pred[test] = block["selected_prediction"]; s1_std[test] = block["selected_std"]
            fit_records.extend([{**fit, "fold": fold} for fit in block["fits"]])
            distances = _nearest_distance(geometry[test], geometry[train])
            for local, index in enumerate(test):
                for angle in range(3):
                    for target, name in enumerate(("R_total", "T_total", "A_balance")):
                        all_oof.append({"candidate": candidate, "contract": "S0", "geometry_index": int(index), "angle_index": angle, "target": name, "truth": float(aggregates[index, angle, target]), "prediction": float(s0_pred[index, angle, target]), "std": float(s0_std[index, angle, target]), "error": float(s0_pred[index, angle, target] - aggregates[index, angle, target]), "fold": fold, "region": regions[index], "nearest_training_distance": float(distances[local])})
                    for target, name in enumerate(("reflection_m0_total", "transmission_m0_total")):
                        all_oof.append({"candidate": candidate, "contract": "S1", "geometry_index": int(index), "angle_index": angle, "target": name, "truth": float(s1_truth[index, angle, target]), "prediction": float(s1_pred[index, angle, target]), "std": float(s1_std[index, angle, target]), "error": float(s1_pred[index, angle, target] - s1_truth[index, angle, target]), "fold": fold, "region": regions[index], "nearest_training_distance": float(distances[local])})
        s0_metrics = {f"A{angle}_{name}": _target_metrics(aggregates[:, angle, target], s0_pred[:, angle, target], s0_std[:, angle, target]) for angle in range(3) for target, name in enumerate(("R_total", "T_total", "A_balance"))}
        s1_metrics = {f"A{angle}_{name}": _target_metrics(s1_truth[:, angle, target], s1_pred[:, angle, target], s1_std[:, angle, target], normalized=True) for angle in range(3) for target, name in enumerate(("reflection_m0_total", "transmission_m0_total"))}
        uncertainty = {
            "minimum_coverage": float(min(item["coverage_95"] for item in list(s0_metrics.values()) + list(s1_metrics.values()))),
            "p95_width_over_N1_sigma": float(max(item["p95_half_width"] / max(item["p95_N1_sigma"], 1.0e-12) for item in list(s0_metrics.values()) + list(s1_metrics.values()))),
            "all_widths_finite_positive": bool(all(item["finite_positive_width"] for item in list(s0_metrics.values()) + list(s1_metrics.values()))),
        }
        candidate_result = {"candidate": candidate, "s0_metrics": s0_metrics, "s1_metrics": s1_metrics, "uncertainty": uncertainty,
                            "physics": {"s0_composition_exact": float(np.max(np.abs(np.sum(s0_pred, axis=2) - 1.0))),
                                        "s1_nonnegative": bool(np.all(s1_pred >= 0.0)),
                                        "s1_selected_le_side": True,
                                        "s1_ledger_exact_by_construction": True},
                            "hard_gate": bool(all(item["nrmse"] <= 0.01 and item["p95_abs"] <= 0.005 and item["max_abs"] <= 0.015 for item in s0_metrics.values()) and all(item["nrmse"] <= 0.02 and item["p95_normalized_N1"] <= 0.75 and item["max_normalized_N1"] <= 2.0 for item in s1_metrics.values()) and uncertainty["minimum_coverage"] >= 0.90 and uncertainty["all_widths_finite_positive"] and uncertainty["p95_width_over_N1_sigma"] <= 1.0)}
        candidate_result["selection_score"] = _score(candidate_result)
        candidate_result["fit_records"] = fit_records
        candidate_runs[candidate] = {"result": candidate_result, "s0_pred": s0_pred, "s0_std": s0_std, "s1_pred": s1_pred, "s1_std": s1_std, "fold": fold_row}
        comparison[candidate] = candidate_result

    eligible = [name for name, run in comparison.items() if run["hard_gate"]]
    selected_candidate = min(eligible or list(comparison), key=lambda name: comparison[name]["selection_score"])
    selected = candidate_runs[selected_candidate]
    oof = [row for row in all_oof if row["candidate"] == selected_candidate]
    recovery = synthetic_recovery(selected_candidate, geometry, aggregates, np.asarray(data["s1_selected_powers"]), latent, side, fractions, folds)
    model_selection = {"schema_version": "task006.training-model-selection-candidate.v1", "status": "training_candidate_review_pending", "selected_candidate": selected_candidate, "selection_basis": "minimum training-only grouped-CV selection_score among hard-gate candidates; if none pass, minimum score is reported without qualification", "eligible_candidates": eligible, "candidate_scores": {name: value["selection_score"] for name, value in comparison.items()}, "training_only": True, "blind_response_accessed": False, "synthetic_recovery": recovery["hard_gate"]}
    outcomes.mkdir(parents=True, exist_ok=True)
    (outcomes / "TRAIN37_MODEL_COMPARISON.json").write_text(json.dumps({"schema_version": "task006.train37-model-comparison.v1", "candidates": comparison, "selected_candidate": selected_candidate, "training_only": True}, indent=2, ensure_ascii=False, default=_json_default) + "\n")
    (outcomes / "TRAIN37_OOF_PREDICTIONS.json").write_text(json.dumps({"schema_version": "task006.train37-oof.v1", "candidate": selected_candidate, "records": oof, "training_only": True}, indent=2, ensure_ascii=False) + "\n")
    (outcomes / "TRAIN37_UNCERTAINTY.json").write_text(json.dumps({"schema_version": "task006.train37-uncertainty.v1", "candidate": selected_candidate, "uncertainty": comparison[selected_candidate]["uncertainty"], "target_metrics": {"s0": comparison[selected_candidate]["s0_metrics"], "s1": comparison[selected_candidate]["s1_metrics"]}, "cross_fitted": True, "training_only": True}, indent=2, ensure_ascii=False) + "\n")
    (outcomes / "TRAIN37_SYNTHETIC_RECOVERY.json").write_text(json.dumps(recovery, indent=2, ensure_ascii=False) + "\n")
    (outcomes / "TRAINING_MODEL_SELECTION_CANDIDATE.json").write_text(json.dumps(model_selection, indent=2, ensure_ascii=False) + "\n")
    return model_selection


def synthetic_recovery(candidate: str, geometry: np.ndarray, aggregates: np.ndarray,
                       s1_truth: np.ndarray, latent: np.ndarray, side: np.ndarray,
                       fractions: np.ndarray, folds: list[tuple[np.ndarray, np.ndarray]]) -> dict[str, Any]:
    """Recover each outer-test geometry from synthetic S0/S1 observations."""

    records = []
    h_grid = np.linspace(115.0, 125.0, 21); w_grid = np.linspace(16.0, 18.0, 21)
    fixed_starts = np.asarray([[115.0,16.0],[115.0,18.0],[125.0,16.0],[125.0,18.0],[120.0,17.0]], dtype=np.float64)
    for fold, (train, test) in enumerate(folds):
        # Fit one outer-training contract per fold and reuse it for every
        # held-out geometry.  No test truth is part of these fits.
        fitted = _fit_contract(candidate, geometry, latent, side, fractions, train, geometry[test], seed=900 + fold * 31)
        fitted_models = fitted["_models"]
        for index in test:
            # Refit a callable model for arbitrary query points using the same
            # outer-training rows; no test truth enters model construction.
            def predict_at(point: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
                q = np.asarray(point, dtype=np.float64).reshape(1, 2)
                b = _predict_fitted_contract(fitted_models, q)
                return b["aggregate_prediction"][0], b["selected_prediction"][0], b["selected_std"][0]
            truth_s0 = aggregates[index]
            truth_s1 = s1_truth[index]
            sigma_s0 = noise_sigma(truth_s0, "N1"); sigma_s1 = noise_sigma(truth_s1, "N1")
            def objective(point: np.ndarray, mode: str) -> float:
                pred0, pred1, _ = predict_at(point)
                if mode == "S1_N1":
                    return float(np.sum(((pred1 - truth_s1) / sigma_s1) ** 2))
                if mode == "S0_N1":
                    return float(np.sum(((pred0 - truth_s0) / sigma_s0) ** 2))
                if mode == "S0_N2":
                    return float(np.sum(((pred0 - truth_s0) / noise_sigma(truth_s0, "N2")) ** 2))
                return float(np.sum(((pred1 - truth_s1) / noise_sigma(truth_s1, "N2")) ** 2))
            grid = np.asarray([[h, w] for h in h_grid for w in w_grid], dtype=np.float64)
            values = np.asarray([objective(point, "S1_N1") for point in grid])
            starts = list(fixed_starts) + [grid[int(np.argmin(values))]]
            fits = []
            for start in starts:
                result = minimize(lambda p: objective(p, "S1_N1"), start, method="L-BFGS-B", bounds=((115.0,125.0),(16.0,18.0)), options={"maxiter":80, "ftol":1.0e-12})
                fits.append(result)
            best = min(fits, key=lambda item: float(item.fun))
            estimate = np.asarray(best.x, dtype=np.float64)
            errors = estimate - geometry[index]
            records.append({"fold": fold, "geometry_index": int(index), "truth_geometry": geometry[index].tolist(), "estimate": estimate.tolist(), "height_error_nm": float(errors[0]), "width_error_nm": float(errors[1]), "objective_S1_N1": float(best.fun), "converged": bool(best.success), "rejected": bool(not best.success), "S0_N1_objective_at_estimate": objective(estimate, "S0_N1"), "S0_N2_objective_at_estimate": objective(estimate, "S0_N2"), "S1_N2_objective_at_estimate": objective(estimate, "S1_N2")})
    height = np.abs(np.asarray([row["height_error_nm"] for row in records])); width = np.abs(np.asarray([row["width_error_nm"] for row in records]))
    summary = {"p95_abs_height_nm": float(np.percentile(height,95)), "p95_abs_width_nm": float(np.percentile(width,95)), "max_abs_height_nm": float(np.max(height)), "max_abs_width_nm": float(np.max(width)), "rejected_count": int(sum(row["rejected"] for row in records))}
    return {"schema_version": "task006.train37-synthetic-recovery.v1", "candidate": candidate, "records": records, "summary": summary, "hard_gate": bool(summary["p95_abs_height_nm"] <= 0.25 and summary["p95_abs_width_nm"] <= 0.05 and summary["max_abs_height_nm"] <= 0.5 and summary["max_abs_width_nm"] <= 0.1 and summary["rejected_count"] == 0), "training_only": True, "test_truth_used_only_as_synthetic_observation": True, "blind_response_accessed": False}


def _json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.float64, np.float32, np.int64, np.int32)):
        return value.item()
    raise TypeError(type(value).__name__)
