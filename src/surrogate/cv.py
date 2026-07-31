"""Training-only PCE/GP candidate evaluation for Task003."""

from __future__ import annotations

import hashlib
import json
import warnings
from dataclasses import asdict
from typing import Any, Callable

import numpy as np
from sklearn.exceptions import ConvergenceWarning

from .dataset import CASE119_ROOT, load_training_dataset
from .features import transform_features
from .folds import FOLD_SEED, fold_identity, folds
from .models import ExactARDGP, PolynomialPCE
from .physics import analytic_power_mask, reconstruct_aggregates
from .targets import channel_table


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def _metrics(truth: np.ndarray, prediction: np.ndarray, *, relative_floor: float = 1.0e-2
             ) -> dict[str, Any]:
    truth = np.asarray(truth, dtype=np.float64)
    prediction = np.asarray(prediction, dtype=np.float64)
    error = prediction - truth
    scale = float(np.ptp(truth)) or 1.0
    significant = truth >= relative_floor
    rel = (np.abs(error[significant]) / np.maximum(np.abs(truth[significant]), relative_floor)
           if np.any(significant) else np.asarray([], dtype=np.float64))
    return {
        "n": int(truth.size),
        "nrmse": float(np.sqrt(np.mean(error ** 2)) / scale),
        "p95_abs": float(np.percentile(np.abs(error), 95)),
        "p95_relative_truth_ge_1e-2": float(np.percentile(rel, 95)) if rel.size else None,
        "max_abs": float(np.max(np.abs(error))),
    }


def _pass_aggregate(metrics: dict[str, Any]) -> bool:
    return (metrics["nrmse"] <= 0.02 and metrics["p95_abs"] <= 1.0e-3
            and (metrics["p95_relative_truth_ge_1e-2"] is None
                 or metrics["p95_relative_truth_ge_1e-2"] <= 0.01))


def _pass_power(metrics: dict[str, Any]) -> bool:
    return metrics["nrmse"] <= 0.02 and metrics["p95_normalized"] <= 1.0


def _pce_predictions(x: np.ndarray, y: np.ndarray, split: list[tuple[np.ndarray, np.ndarray]],
                     degree: int) -> np.ndarray:
    prediction = np.full(len(y), np.nan)
    for train, test in split:
        prediction[test] = PolynomialPCE(degree).fit(x[train], y[train]).predict(x[test])
    return prediction


def _gp_predictions(x: np.ndarray, y: np.ndarray, split: list[tuple[np.ndarray, np.ndarray]],
                    *, log_target: bool = False) -> np.ndarray:
    prediction = np.full(len(y), np.nan)
    for train, test in split:
        train_y = np.log1p(np.maximum(y[train], 0.0)) if log_target else y[train]
        model = ExactARDGP(jitter=1.0e-10, optimizer_restarts=0, random_state=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            model.fit(x[train], train_y)
        value = model.predict(x[test])
        prediction[test] = np.expm1(value) if log_target else value
    return prediction


def _power_cv(x: np.ndarray, powers: np.ndarray, mask: np.ndarray,
              split: list[tuple[np.ndarray, np.ndarray]], channels: list[Any]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for channel in channels:
        truth = powers[:, channel.order_index, 0 if channel.component == "s" else 1]
        active = mask[:, channel.order_index, 0 if channel.component == "s" else 1]
        prediction = np.full(len(x), np.nan)
        for train, test in split:
            train_active = train[active[train]]
            test_active = test[active[test]]
            if len(train_active) < 3 or len(test_active) == 0:
                continue
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ConvergenceWarning)
                model = ExactARDGP(jitter=1.0e-10, optimizer_restarts=0,
                                   random_state=0).fit(
                    x[train_active], np.log1p(np.maximum(truth[train_active], 0.0)))
            prediction[test_active] = np.maximum(np.expm1(model.predict(x[test_active])), 0.0)
        valid = active & np.isfinite(prediction)
        if not np.any(valid):
            reports.append({"channel": channel.key(), "status": "insufficient_training_support",
                            "active_count": int(active.sum())})
            continue
        error = prediction[valid] - truth[valid]
        scale = float(np.ptp(truth[valid])) or 1.0
        normalized = np.abs(error) / np.sqrt((0.01 * np.maximum(truth[valid], 0.0)) ** 2
                                              + 1.0e-8 ** 2)
        metric = {"channel": channel.key(), "order_index": channel.order_index,
                  "maximum_training_power": channel.maximum_training_power,
                  "active_count": int(valid.sum()),
                  "nrmse": float(np.sqrt(np.mean(error ** 2)) / scale),
                  "p95_abs": float(np.percentile(np.abs(error), 95)),
                  "p95_normalized": float(np.percentile(normalized, 95)),
                  "max_abs": float(np.max(np.abs(error))),
                  "hard_gate": bool(float(np.sqrt(np.mean(error ** 2)) / scale) <= 0.02
                                     and float(np.percentile(normalized, 95)) <= 1.0)}
        reports.append(metric)
    return reports


def run_training_cv() -> dict[str, Any]:
    dataset = load_training_dataset(CASE119_ROOT)
    x = transform_features(dataset.inputs)
    split = folds(x, n_splits=5, seed=FOLD_SEED)
    fold_meta = fold_identity(x, split, seed=FOLD_SEED)
    aggregates = dataset.aggregates
    aggregate_report: dict[str, Any] = {}
    for index, name in enumerate(("R_total", "T_total", "A_balance")):
        pce2 = _pce_predictions(x, aggregates[:, index], split, 2)
        pce3 = _pce_predictions(x, aggregates[:, index], split, 3)
        gp = _gp_predictions(x, aggregates[:, index], split)
        aggregate_report[name] = {
            "pce_degree2": _metrics(aggregates[:, index], pce2),
            "pce_degree3": _metrics(aggregates[:, index], pce3),
            "exact_gp": _metrics(aggregates[:, index], gp),
            "selected_candidate": "exact_gp",
            "hard_gate": _pass_aggregate(_metrics(aggregates[:, index], gp)),
        }
    projected_gp = np.column_stack([
        _gp_predictions(x, aggregates[:, index], split) for index in range(3)
    ])
    projected = reconstruct_aggregates(projected_gp)
    projected_metrics = {
        name: _metrics(aggregates[:, index], projected[:, index])
        for index, name in enumerate(("R_total", "T_total", "A_balance"))
    }
    order_identity = json.loads((CASE119_ROOT / "order_identity.json").read_text())
    channels = channel_table(order_identity, dataset.order_powers,
                             dataset.power_carrying_mask)
    power_report = _power_cv(x, dataset.order_powers, dataset.power_carrying_mask,
                             split, channels)
    aggregate_pass = all(item["hard_gate"] for item in aggregate_report.values())
    power_pass = all(item.get("hard_gate", False) for item in power_report)
    report = {
        "status": "pass" if aggregate_pass and power_pass else "hard_gate_failure",
        "dataset_id": dataset.dataset_id,
        "training_count": dataset.n_samples,
        "folds": fold_meta,
        "aggregate_metrics": aggregate_report,
        "aggregate_projected_metrics": projected_metrics,
        "primary_power_channels": [asdict(channel) | {"key": channel.key()} for channel in channels],
        "primary_power_metrics": power_report,
        "aggregate_hard_gate": aggregate_pass,
        "primary_power_hard_gate": power_pass,
        "validation_target_accessed": False,
        "active_learning": {"required": not (aggregate_pass and power_pass),
                             "round_budget": 3, "points_per_round": 8,
                             "points_used": 0},
        "model_selection": "exact_gp" if aggregate_pass and power_pass else "blocked_before_lock",
        "feature_contract_sha256": _hash({"features": ["h_scaled", "w_scaled", "kx_over_k0", "ky_over_k0"]}),
    }
    return report

