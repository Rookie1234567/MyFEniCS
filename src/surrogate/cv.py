"""Training-only M3R candidate comparison and auditable OOF diagnostics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

import numpy as np

from .dataset import CASE119_ROOT, load_training_dataset
from .features import feature_contracts, transform_feature_candidate
from .folds import FOLD_SEED, fold_identity, folds
from .models import ExactARDGP, OrthogonalPCE
from .physics import analytic_power_mask, reconstruct_aggregates
from .targets import (AGGREGATE_NAMES, aggregate_log_ratios, channel_table,
                      freeze_power_floor)


FEATURE_CANDIDATES = ("A", "B", "C")
PRIMARY_AGGREGATE_NAMES = ("R_total", "T_total", "A_balance")
PCE_CANDIDATES = (
    ("legendre", 2), ("legendre", 3),
    ("chebyshev", 2), ("chebyshev", 3),
)


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def _metrics(truth: np.ndarray, prediction: np.ndarray, *, relative_floor: float = 1.0e-2
             ) -> dict[str, Any]:
    truth = np.asarray(truth, dtype=np.float64)
    prediction = np.asarray(prediction, dtype=np.float64)
    valid = np.isfinite(truth) & np.isfinite(prediction)
    if not np.any(valid):
        return {"n": 0, "nrmse": None, "p95_abs": None,
                "p95_relative_truth_ge_1e-2": None, "max_abs": None}
    truth, prediction = truth[valid], prediction[valid]
    error = prediction - truth
    scale = float(np.ptp(truth)) or 1.0
    significant = truth >= relative_floor
    rel = np.abs(error[significant]) / np.maximum(np.abs(truth[significant]), relative_floor)
    return {
        "n": int(truth.size),
        "nrmse": float(np.sqrt(np.mean(error ** 2)) / scale),
        "p95_abs": float(np.percentile(np.abs(error), 95)),
        "p95_relative_truth_ge_1e-2": float(np.percentile(rel, 95)) if rel.size else None,
        "max_abs": float(np.max(np.abs(error))),
    }


def _pass_aggregate(metrics: dict[str, Any]) -> bool:
    return (metrics["nrmse"] is not None and metrics["nrmse"] <= 0.02
            and metrics["p95_abs"] <= 1.0e-3
            and (metrics["p95_relative_truth_ge_1e-2"] is None
                 or metrics["p95_relative_truth_ge_1e-2"] <= 0.01))


def _pass_power(metrics: dict[str, Any]) -> bool:
    return (metrics.get("nrmse") is not None
            and metrics["nrmse"] <= 0.02
            and metrics["p95_normalized"] <= 1.0)


def _selection_score(metrics: dict[str, dict[str, Any]]) -> float:
    scores: list[float] = []
    for metric in metrics.values():
        if metric["nrmse"] is None:
            return float("inf")
        scores.extend((metric["nrmse"] / 0.02,
                       metric["p95_abs"] / 1.0e-3,
                       (metric["p95_relative_truth_ge_1e-2"] or 0.0) / 0.01))
    return float(max(scores))


def _regions(points: np.ndarray) -> list[list[str]]:
    values = np.asarray(points, dtype=np.float64)
    grazing = np.deg2rad(values[:, 2]); azimuth = np.deg2rad(values[:, 3])
    kx = np.cos(grazing) * np.cos(azimuth); ky = np.cos(grazing) * np.sin(azimuth)
    labels: list[list[str]] = []
    for index, row in enumerate(values):
        current: list[str] = []
        if row[2] <= 2.0:
            current.append("low_grazing")
        if row[3] >= 75.0:
            current.append("high_azimuth")
        if row[0] in (115.0, 125.0) or row[1] in (16.0, 18.0):
            current.append("geometry_extreme")
        nonzero_margin = [abs(1.0 - ((kx[index] + m * 13.5 / 50.0) ** 2 + ky[index] ** 2))
                          for m in range(-7, 0)]
        if min(nonzero_margin) <= 0.02:
            current.append("cutoff")
        if not current:
            current.append("interior")
        labels.append(current)
    return labels


def _region_metrics(truth: np.ndarray, prediction: np.ndarray, regions: list[list[str]],
                    *, active: np.ndarray | None = None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    names = sorted({name for row in regions for name in row})
    for name in names:
        selected = np.asarray([name in row for row in regions], dtype=bool)
        if active is not None:
            selected &= np.asarray(active, dtype=bool)
        result[name] = _metrics(np.asarray(truth)[selected], np.asarray(prediction)[selected])
    return result


def _composition_std(latent_std: np.ndarray, composition: np.ndarray) -> np.ndarray:
    """Delta-method uncertainty for softmax(zR,zT,0)."""

    p = composition[:, :3]
    sr = np.asarray(latent_std[:, 0], dtype=np.float64)
    st = np.asarray(latent_std[:, 1], dtype=np.float64)
    jr = p * (np.eye(3)[0][None, :] - p[:, 0, None])
    jt = p * (np.eye(3)[1][None, :] - p[:, 1, None])
    std = np.sqrt(np.maximum((jr * sr[:, None]) ** 2 + (jt * st[:, None]) ** 2, 0.0))
    return np.column_stack((std, std[:, 2]))


def _fit_gp_oof(x: np.ndarray, latent: np.ndarray,
                split: list[tuple[np.ndarray, np.ndarray]], *, seed: int
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict[str, Any]]]:
    prediction = np.full_like(latent, np.nan, dtype=np.float64)
    standard_deviation = np.full_like(latent, np.nan, dtype=np.float64)
    fold_for_row = np.full(len(x), -1, dtype=np.int64)
    fits: list[dict[str, Any]] = []
    for fold_index, (train, test) in enumerate(split):
        fold_for_row[test] = fold_index
        for latent_index, name in enumerate(("zR", "zT")):
            model = ExactARDGP(jitter=1.0e-10, optimizer_restarts=8,
                               random_state=seed + latent_index)
            model.fit(x[train], latent[train, latent_index])
            mean, std = model.predict(x[test], return_std=True)
            prediction[test, latent_index] = mean
            standard_deviation[test, latent_index] = std
            fits.append({"fold": fold_index, "latent": name, **model.metadata()})
    return prediction, standard_deviation, fold_for_row, fits


def _fit_pce_oof(x: np.ndarray, latent: np.ndarray,
                 split: list[tuple[np.ndarray, np.ndarray]], *, kind: str, degree: int
                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict[str, Any]]]:
    prediction = np.full_like(latent, np.nan, dtype=np.float64)
    standard_deviation = np.full_like(latent, np.nan, dtype=np.float64)
    fold_for_row = np.full(len(x), -1, dtype=np.int64)
    fits: list[dict[str, Any]] = []
    for fold_index, (train, test) in enumerate(split):
        fold_for_row[test] = fold_index
        for latent_index, name in enumerate(("zR", "zT")):
            model = OrthogonalPCE(degree=degree, kind=kind).fit(
                x[train], latent[train, latent_index])
            prediction[test, latent_index] = model.predict(x[test])
            fits.append({"fold": fold_index, "latent": name, **model.metadata()})
    return prediction, standard_deviation, fold_for_row, fits


def _power_oof(x: np.ndarray, powers: np.ndarray, mask: np.ndarray,
               split: list[tuple[np.ndarray, np.ndarray]], channels: list[Any],
               *, kind: str, degree: int | None, seed: int
               ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    reports: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    fit_details: list[dict[str, Any]] = []
    region_labels = _regions(_POWER_POINTS)
    for channel in channels:
        component_index = 0 if channel.component == "s" else 1
        truth = powers[:, channel.order_index, component_index]
        active = mask[:, channel.order_index, component_index]
        floor = freeze_power_floor(truth, active)
        prediction = np.full(len(x), np.nan, dtype=np.float64)
        standard_deviation = np.full(len(x), np.nan, dtype=np.float64)
        fold_for_row = np.full(len(x), -1, dtype=np.int64)
        for fold_index, (train, test) in enumerate(split):
            train_active = train[active[train]]; test_active = test[active[test]]
            fold_for_row[test] = fold_index
            if len(train_active) < 3 or len(test_active) == 0:
                continue
            if kind == "exact_gp":
                model = ExactARDGP(jitter=1.0e-10, optimizer_restarts=8,
                                   random_state=seed)
            else:
                model = OrthogonalPCE(degree=int(degree), kind=kind)
            model.fit(x[train_active], np.log(truth[train_active] + floor))
            fit_details.append({"channel": channel.key(), "fold": fold_index,
                                **model.metadata()})
            if kind == "exact_gp":
                latent_mean, latent_std = model.predict(x[test_active], return_std=True)
                standard_deviation[test_active] = (np.exp(latent_mean) * latent_std)
            else:
                latent_mean = model.predict(x[test_active])
            prediction[test_active] = np.maximum(np.exp(latent_mean) - floor, 0.0)
        valid = active & np.isfinite(prediction)
        if not np.any(valid):
            reports.append({"channel": channel.key(), "status": "insufficient_training_support",
                            "floor": floor, "active_count": int(active.sum())})
            continue
        error = prediction[valid] - truth[valid]
        scale = float(np.ptp(truth[valid])) or 1.0
        normalized = np.abs(error) / np.sqrt((0.01 * np.maximum(truth[valid], 0.0)) ** 2
                                              + 1.0e-8 ** 2)
        metrics = {"channel": channel.key(), "order_index": channel.order_index,
                   "maximum_training_power": channel.maximum_training_power,
                   "active_count": int(valid.sum()), "floor": floor,
                   "nrmse": float(np.sqrt(np.mean(error ** 2)) / scale),
                   "p95_abs": float(np.percentile(np.abs(error), 95)),
                   "p95_normalized": float(np.percentile(normalized, 95)),
                   "max_abs": float(np.max(np.abs(error))),
                   "hard_gate": bool(float(np.sqrt(np.mean(error ** 2)) / scale) <= 0.02
                                      and float(np.percentile(normalized, 95)) <= 1.0),
                   "region_breakdown": _region_metrics(truth, prediction, region_labels,
                                                       active=valid)}
        reports.append(metrics)
        for row in range(len(x)):
            records.append({"target_type": "order_power", "channel": channel.key(),
                            "sample_index": row, "fold": int(fold_for_row[row]),
                            "truth": float(truth[row]) if active[row] else None,
                            "prediction": float(prediction[row]) if np.isfinite(prediction[row]) else None,
                            "std": float(standard_deviation[row]) if np.isfinite(standard_deviation[row]) else None,
                            "error": float(prediction[row] - truth[row]) if np.isfinite(prediction[row]) else None,
                            "power_carrying": bool(active[row]),
                            "regions": region_labels[row]})
    return reports, records, fit_details


def _aggregate_records(points: np.ndarray, truth: np.ndarray, prediction: np.ndarray,
                       standard_deviation: np.ndarray, fold: np.ndarray,
                       regions: list[list[str]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in range(len(points)):
        for index, name in enumerate(PRIMARY_AGGREGATE_NAMES):
            records.append({"target_type": "aggregate", "target": name,
                            "sample_index": row, "fold": int(fold[row]),
                            "truth": float(truth[row, index]),
                            "prediction": float(prediction[row, index]),
                            "std": float(standard_deviation[row, index]),
                            "error": float(prediction[row, index] - truth[row, index]),
                            "power_carrying": None, "regions": regions[row]})
    return records


def _aggregate_result(points: np.ndarray, aggregates: np.ndarray,
                      latent_prediction: np.ndarray, latent_std: np.ndarray,
                      fold: np.ndarray, fits: list[dict[str, Any]], *, candidate: str
                      ) -> dict[str, Any]:
    truth = aggregates[:, :3]
    prediction = reconstruct_aggregates(latent_prediction)
    standard_deviation = _composition_std(latent_std, prediction)
    metrics = {name: _metrics(truth[:, index], prediction[:, index])
               for index, name in enumerate(PRIMARY_AGGREGATE_NAMES)}
    regions = _regions(points)
    return {
        "candidate": candidate, "metrics": metrics,
        "selection_score": _selection_score(metrics),
        "hard_gate": all(_pass_aggregate(item) for item in metrics.values()),
        "region_breakdown": {name: _region_metrics(truth[:, index], prediction[:, index], regions)
                             for index, name in enumerate(PRIMARY_AGGREGATE_NAMES)},
        "fold_model_fits": fits,
        "latent_prediction": latent_prediction,
        "latent_std": latent_std,
        "prediction": prediction,
        "standard_deviation": standard_deviation,
        "fold": fold,
    }


# Set during run_training_cv so the power helper can carry the same 96-point
# region labels without opening any non-training array.
_POWER_POINTS: np.ndarray = np.empty((0, 4), dtype=np.float64)


def run_training_cv() -> dict[str, Any]:
    """Run the corrected M3R comparison on the same 96 training rows."""

    global _POWER_POINTS
    dataset = load_training_dataset(CASE119_ROOT)
    _POWER_POINTS = dataset.inputs
    split = folds(transform_feature_candidate(dataset.inputs, "A"), n_splits=5, seed=FOLD_SEED)
    fold_meta = fold_identity(transform_feature_candidate(dataset.inputs, "A"), split, seed=FOLD_SEED)
    aggregates = dataset.aggregates
    latent_truth = aggregate_log_ratios(aggregates)
    candidate_results: list[dict[str, Any]] = []
    for feature in FEATURE_CANDIDATES:
        x = transform_feature_candidate(dataset.inputs, feature)
        gp_latent, gp_std, gp_fold, gp_fits = _fit_gp_oof(x, latent_truth, split, seed=17)
        candidate_results.append(_aggregate_result(
            dataset.inputs, aggregates, gp_latent, gp_std, gp_fold, gp_fits,
            candidate=f"exact_gp:features={feature}"))
        for kind, degree in PCE_CANDIDATES:
            pce_latent, pce_std, pce_fold, pce_fits = _fit_pce_oof(
                x, latent_truth, split, kind=kind, degree=degree,
            )
            candidate_results.append(_aggregate_result(
                dataset.inputs, aggregates, pce_latent, pce_std, pce_fold, pce_fits,
                candidate=f"{kind}_degree{degree}:features={feature}"))

    selected = min(candidate_results, key=lambda item: (item["selection_score"], item["candidate"]))
    selected_name = selected["candidate"]
    family, feature_fragment = selected_name.split(":features=")
    selected_feature = feature_fragment
    if family == "exact_gp":
        selected_kind, selected_degree = "exact_gp", None
    else:
        selected_kind, selected_degree = family.split("_degree")
        selected_degree = int(selected_degree)
    selected_power_metrics, power_records, power_fit_details = _power_oof(
        transform_feature_candidate(dataset.inputs, selected_feature),
        dataset.order_powers, dataset.power_carrying_mask, split,
        channel_table(json.loads((CASE119_ROOT / "order_identity.json").read_text()),
                      dataset.order_powers, dataset.power_carrying_mask),
        kind=selected_kind, degree=selected_degree, seed=29,
    )
    selected_records = _aggregate_records(
        dataset.inputs, aggregates, selected["prediction"], selected["standard_deviation"],
        selected["fold"], _regions(dataset.inputs),
    ) + power_records
    selected_power_pass = all(item.get("hard_gate", False) for item in selected_power_metrics)
    selected_aggregate_pass = bool(selected["hard_gate"])
    aggregate_std = selected["standard_deviation"]
    aggregate_error = selected["prediction"][:, :3] - aggregates[:, :3]
    standardized = np.abs(aggregate_error) / np.maximum(aggregate_std[:, :3], 1.0e-12)
    coverage = float(np.mean(standardized <= 1.96)) if np.all(np.isfinite(aggregate_std)) else 0.0
    uncertainty_reliable = bool(np.all(np.isfinite(aggregate_std)) and 0.80 <= coverage <= 1.0)
    candidate_summary = []
    for item in candidate_results:
        candidate_summary.append({key: item[key] for key in
                                  ("candidate", "metrics", "selection_score", "hard_gate",
                                   "region_breakdown", "fold_model_fits")})
    report = {
        "status": "pass" if selected_aggregate_pass and selected_power_pass else "hard_gate_failure",
        "dataset_id": dataset.dataset_id, "training_count": dataset.n_samples,
        "folds": fold_meta, "feature_candidates": feature_contracts(),
        "aggregate_latent": {"zR": "log((R+eps)/(A+eps))", "zT": "log((T+eps)/(A+eps))",
                              "epsilon": 1.0e-8, "reconstruction": "softmax(zR,zT,0)"},
        "candidate_diagnostics": candidate_summary,
        "selected_candidate": selected_name,
        "selected_feature_candidate": selected_feature,
        "selected_model_family": selected_kind,
        "selected_degree": selected_degree,
        "selected_aggregate_metrics": selected["metrics"],
        "selected_aggregate_region_breakdown": selected["region_breakdown"],
        "selected_power_metrics": selected_power_metrics,
        "selected_power_fit_details": power_fit_details,
        "aggregate_hard_gate": selected_aggregate_pass,
        "primary_power_hard_gate": selected_power_pass,
        "uncertainty_diagnostics": {"aggregate_95pct_coverage": coverage,
                                    "reliable_for_acquisition": uncertainty_reliable,
                                    "standardized_residual_definition": "abs(error)/predicted_std"},
        "oof_record_count": len(selected_records),
        "oof_records": selected_records,
        "validation_target_accessed": False,
        "active_learning": {
            "required": not (selected_aggregate_pass and selected_power_pass),
            "round_budget": 3, "points_per_round": 8, "points_used": 0,
            "first_round_plan": None if not uncertainty_reliable else "eligible_for_review_only",
            "fem_started": False,
        },
        "model_selection": "candidate_selected_training_only_no_lock" if not (
            selected_aggregate_pass and selected_power_pass) else "candidate_ready_for_lock",
        "feature_contract_sha256": _hash(feature_contracts()),
    }
    return report
