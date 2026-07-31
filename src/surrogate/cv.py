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
from .models import ExactARDGP, OrthogonalPCE, TrendResidualGP
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


def _fit_m3s_oof(x: np.ndarray, latent: np.ndarray,
                 split: list[tuple[np.ndarray, np.ndarray]], *, family: str,
                 jitter: float, seed: int
                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """OOF fit for the finite M3S G1/G2 comparison on frozen feature B."""
    prediction = np.full_like(latent, np.nan, dtype=np.float64)
    standard_deviation = np.full_like(latent, np.nan, dtype=np.float64)
    fold_for_row = np.full(len(x), -1, dtype=np.int64)
    fits: list[dict[str, Any]] = []
    for fold_index, (train, test) in enumerate(split):
        fold_for_row[test] = fold_index
        for latent_index, name in enumerate(("zR", "zT")):
            if family == "G1_constant_gp":
                model = ExactARDGP(jitter=jitter, optimizer_restarts=8,
                                   random_state=seed + latent_index)
            elif family == "G2_degree2_trend_residual_gp":
                model = TrendResidualGP(jitter=jitter, optimizer_restarts=8,
                                        random_state=seed + latent_index)
            else:
                raise ValueError(f"unsupported M3S family: {family}")
            model.fit(x[train], latent[train, latent_index])
            mean, std = model.predict(x[test], return_std=True)
            prediction[test, latent_index] = mean
            standard_deviation[test, latent_index] = std
            fits.append({"fold": fold_index, "latent": name,
                         "family": family, "jitter": jitter, **model.metadata()})
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


def _power_fraction_oof(x: np.ndarray, aggregates: np.ndarray,
                        aggregate_prediction: np.ndarray, powers: np.ndarray,
                        mask: np.ndarray, split: list[tuple[np.ndarray, np.ndarray]],
                        channels: list[Any], *, seed: int,
                        jitter: float = 1.0e-10
                        ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """P2 side-total plus masked channel-fraction OOF reconstruction."""
    n = len(x)
    raw = np.full((n, 22, 2), np.nan, dtype=np.float64)
    raw_std = np.full_like(raw, np.nan)
    fit_details: list[dict[str, Any]] = []
    regions = _regions(_POWER_POINTS)
    for channel in channels:
        oi = channel.order_index; ci = 0 if channel.component == "s" else 1
        side = 0 if oi < 11 else 1
        active = mask[:, oi, ci]
        side_total = np.asarray(aggregates[:, side], dtype=np.float64)
        truth_fraction = np.divide(
            powers[:, oi, ci], side_total,
            out=np.zeros(n, dtype=np.float64), where=active & (side_total > 0.0),
        )
        floor = freeze_power_floor(truth_fraction, active)
        for fold_index, (train, test) in enumerate(split):
            train_active = train[active[train] & np.isfinite(truth_fraction[train])]
            test_active = test[active[test]]
            if len(train_active) < 3 or len(test_active) == 0:
                continue
            model = ExactARDGP(jitter=jitter, optimizer_restarts=8,
                               random_state=seed + oi * 3 + ci)
            model.fit(x[train_active], np.log(truth_fraction[train_active] + floor))
            mean, std = model.predict(x[test_active], return_std=True)
            raw[test_active, oi, ci] = np.maximum(np.exp(mean) - floor, 0.0)
            raw_std[test_active, oi, ci] = np.exp(mean) * std
            fit_details.append({"channel": channel.key(), "fold": fold_index,
                                "fraction_floor": floor, **model.metadata()})
    fraction = np.full_like(raw, np.nan)
    fraction_std = np.full_like(raw_std, np.nan)
    for row in range(n):
        for side in (0, 1):
            sl = slice(0, 11) if side == 0 else slice(11, 22)
            active = mask[row, sl, :]
            values = np.where(active & np.isfinite(raw[row, sl, :]), raw[row, sl, :], 0.0)
            denom = float(np.sum(values))
            if denom <= 0.0:
                continue
            fraction[row, sl, :] = np.where(active, values / denom, np.nan)
            finite_std = np.where(active & np.isfinite(raw_std[row, sl, :]), raw_std[row, sl, :], 0.0)
            fraction_std[row, sl, :] = np.where(active, finite_std / denom, np.nan)
    reconstructed = np.full_like(raw, np.nan)
    reconstructed_std = np.full_like(raw_std, np.nan)
    for side in (0, 1):
        sl = slice(0, 11) if side == 0 else slice(11, 22)
        reconstructed[:, sl, :] = fraction[:, sl, :] * aggregate_prediction[:, side, None, None]
        reconstructed_std[:, sl, :] = fraction_std[:, sl, :] * aggregate_prediction[:, side, None, None]
    reports: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for channel in channels:
        oi = channel.order_index; ci = 0 if channel.component == "s" else 1
        active = mask[:, oi, ci]
        truth = powers[:, oi, ci]
        prediction = reconstructed[:, oi, ci]
        valid = active & np.isfinite(prediction)
        if not np.any(valid):
            continue
        metrics = _metrics(truth[valid], prediction[valid])
        error = prediction[valid] - truth[valid]
        normalized = np.abs(error) / np.sqrt((0.01 * np.maximum(truth[valid], 0.0)) ** 2 + 1.0e-8 ** 2)
        report = {"channel": channel.key(), "order_index": oi,
                  "maximum_training_power": channel.maximum_training_power,
                  "active_count": int(valid.sum()), "fraction_reconstruction": True,
                  **metrics, "p95_normalized": float(np.percentile(normalized, 95)),
                  "max_abs": float(np.max(np.abs(error))),
                  "hard_gate": bool(metrics["nrmse"] <= 0.02 and np.percentile(normalized, 95) <= 1.0),
                  "region_breakdown": _region_metrics(truth, prediction, regions, active=valid)}
        reports.append(report)
        for row in range(n):
            records.append({"target_type": "order_power_p2", "channel": channel.key(),
                            "sample_index": row, "truth": float(truth[row]) if active[row] else None,
                            "prediction": float(prediction[row]) if np.isfinite(prediction[row]) else None,
                            "std": float(reconstructed_std[row, oi, ci]) if np.isfinite(reconstructed_std[row, oi, ci]) else None,
                            "error": float(prediction[row] - truth[row]) if np.isfinite(prediction[row]) else None,
                            "power_carrying": bool(active[row]), "regions": regions[row]})
    ledgers = {"reflection": [], "transmission": []}
    for side, name in ((0, "reflection"), (1, "transmission")):
        sl = slice(0, 11) if side == 0 else slice(11, 22)
        ledger = np.nansum(np.where(mask[:, sl, :], reconstructed[:, sl, :], 0.0), axis=(1, 2))
        ledgers[name] = {"max_abs_error": float(np.max(np.abs(ledger - aggregate_prediction[:, side]))),
                         "mean_abs_error": float(np.mean(np.abs(ledger - aggregate_prediction[:, side])))}
    return reports, records, fit_details, {"side_ledger": ledgers,
        "reconstructed_power": reconstructed, "reconstructed_std": reconstructed_std,
        "fraction": fraction}


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


def run_training_cv(dataset_dir=CASE119_ROOT) -> dict[str, Any]:
    """Run the corrected M3R comparison on the same 96 training rows."""

    global _POWER_POINTS
    dataset = load_training_dataset(dataset_dir)
    _POWER_POINTS = dataset.inputs
    frozen_x = transform_feature_candidate(dataset.inputs, "B")
    split = folds(frozen_x, n_splits=5, seed=FOLD_SEED)
    fold_meta = fold_identity(frozen_x, split, seed=FOLD_SEED)
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

    # M3S model closure: only constant GP and degree-2 orthogonal trend plus GP
    # residual, all on the frozen feature-B contract and three allowed jitters.
    m3s_results: list[dict[str, Any]] = []
    for family in ("G1_constant_gp", "G2_degree2_trend_residual_gp"):
        for jitter in (1.0e-10, 1.0e-8, 1.0e-6):
            pred, std, fold, fits = _fit_m3s_oof(
                frozen_x, latent_truth, split, family=family, jitter=jitter, seed=41,
            )
            m3s_results.append(_aggregate_result(
                dataset.inputs, aggregates, pred, std, fold, fits,
                candidate=f"{family}:features=B:jitter={jitter:.0e}"))
    selected = min(m3s_results, key=lambda item: (item["selection_score"], item["candidate"]))
    selected_name = selected["candidate"]
    selected_family = selected_name.split(":features=")[0]
    selected_feature = "B"
    selected_jitter = float(selected_name.rsplit("=", 1)[1])
    selected_kind, selected_degree = selected_family, (2 if selected_family.startswith("G2") else None)
    # P1 remains an explicit independent-log-power diagnostic.  The physical
    # P2 ledger below is the only reconstructed power candidate used for the
    # active-learning ranking.
    selected_power_metrics, power_records, power_fit_details = _power_oof(
        frozen_x,
        dataset.order_powers, dataset.power_carrying_mask, split,
        channel_table(json.loads((dataset_dir / "order_identity.json").read_text()),
                      dataset.order_powers, dataset.power_carrying_mask),
        kind="exact_gp", degree=None, seed=29,
    )
    channels = channel_table(json.loads((dataset_dir / "order_identity.json").read_text()),
                             dataset.order_powers, dataset.power_carrying_mask)
    p2_metrics, p2_records, p2_fit_details, p2_ledger = _power_fraction_oof(
        frozen_x, aggregates, selected["prediction"], dataset.order_powers,
        dataset.power_carrying_mask, split, channels, seed=71, jitter=selected_jitter,
    )
    selected_records = _aggregate_records(
        dataset.inputs, aggregates, selected["prediction"], selected["standard_deviation"],
        selected["fold"], _regions(dataset.inputs),
    ) + power_records + p2_records
    selected_power_pass = all(item.get("hard_gate", False) for item in p2_metrics)
    selected_aggregate_pass = bool(selected["hard_gate"])
    aggregate_std = selected["standard_deviation"]
    aggregate_error = selected["prediction"][:, :3] - aggregates[:, :3]
    standardized = np.abs(aggregate_error) / np.maximum(aggregate_std[:, :3], 1.0e-12)
    coverage = float(np.mean(standardized <= 1.96)) if np.all(np.isfinite(aggregate_std)) else 0.0
    calibration_factor = float(max(1.0, np.percentile(standardized[np.isfinite(standardized)], 95) / 1.96))
    calibrated_std = aggregate_std[:, :3] * calibration_factor
    calibrated_standardized = np.abs(aggregate_error) / np.maximum(calibrated_std, 1.0e-12)
    calibrated_coverage = float(np.mean(calibrated_standardized <= 1.96))
    region_labels = _regions(dataset.inputs)
    region_uncertainty = {}
    for region in sorted({name for row in region_labels for name in row}):
        selected_region = np.asarray([region in row for row in region_labels])
        region_uncertainty[region] = {
            "count": int(np.sum(selected_region)),
            "raw_95pct_coverage": float(np.mean(standardized[selected_region] <= 1.96)),
            "calibrated_95pct_coverage": float(np.mean(calibrated_standardized[selected_region] <= 1.96)),
            "standardized_residual_p50": float(np.percentile(standardized[selected_region], 50)),
            "standardized_residual_p95": float(np.percentile(standardized[selected_region], 95)),
        }
    uncertainty_reliable = bool(np.all(np.isfinite(aggregate_std)) and 0.80 <= coverage <= 1.0)
    identity = json.loads((dataset_dir / "order_identity.json").read_text())
    channel_tiers = []
    for oi, order in enumerate(identity["axis"]):
        for ci, component in enumerate(("s", "p")):
            active = dataset.power_carrying_mask[:, oi, ci]
            values = dataset.order_powers[:, oi, ci]
            maximum = float(np.nanmax(values)) if np.any(active) else 0.0
            if maximum >= 1.0e-4 and int(active.sum()) >= 24:
                tier = "primary"
            elif maximum >= 1.0e-6:
                tier = "secondary"
            else:
                tier = "structural-null"
            channel_tiers.append({"channel": f"{order['side']}:m{order['m']}:{component}",
                                  "tier": tier, "maximum_training_power": maximum,
                                  "active_training_count": int(active.sum()),
                                  "inactive_semantics": "null"})
    candidate_summary = []
    for item in candidate_results + m3s_results:
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
        "m3s_model_comparison": [{key: item[key] for key in
                                   ("candidate", "metrics", "selection_score", "hard_gate",
                                    "region_breakdown", "fold_model_fits")}
                                  for item in m3s_results],
        "selected_candidate": selected_name,
        "selected_feature_candidate": selected_feature,
        "selected_model_family": selected_kind,
        "selected_degree": selected_degree,
        "selected_jitter": selected_jitter,
        "selected_aggregate_metrics": selected["metrics"],
        "selected_aggregate_region_breakdown": selected["region_breakdown"],
        "selected_power_metrics": selected_power_metrics,
        "selected_power_fit_details": power_fit_details,
        "selected_power_physical_metrics": p2_metrics,
        "selected_power_physical_fit_details": p2_fit_details,
        "selected_power_physical_ledger": p2_ledger["side_ledger"],
        "power_reconstruction": {
            "P1": "independent log(P+training_floor), diagnostic only",
            "P2": "predicted side-total + masked active-channel fractions",
            "P2_active_fraction_sum": "one per top/bottom side and OOF row",
            "inactive_semantics": "null",
        },
        "aggregate_hard_gate": selected_aggregate_pass,
        "primary_power_hard_gate": selected_power_pass,
        "uncertainty_diagnostics": {"aggregate_95pct_coverage": coverage,
                                    "multiplicative_training_oof_calibration_factor": calibration_factor,
                                    "calibrated_aggregate_95pct_coverage": calibrated_coverage,
                                    "region_breakdown": region_uncertainty,
                                    "standardized_residual_quantiles": {
                                        "p50": float(np.percentile(standardized, 50)),
                                        "p95": float(np.percentile(standardized, 95)),
                                    },
                                    "reliable_for_acquisition": uncertainty_reliable,
                                    "standardized_residual_definition": "abs(error)/predicted_std"},
        "power_channel_tiers": channel_tiers,
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
