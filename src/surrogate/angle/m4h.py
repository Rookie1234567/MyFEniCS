"""Required M4H: training-only selective angle surrogate qualification.

M4H is deliberately response-limited.  It consumes the immutable train112
package and the angle-only candidate/blind designs, but never opens a blind
response.  The two risk rules are finite, auditable contracts: S1 is the
pre-frozen M4E2 monotone ensemble and S2 is the maximum of calibrated
Matérn standard deviation and the two approved model disagreements.

The important distinction in this module is between *structural support* and
*selective acceptance*.  Structural support is a response-blind geometry and
topology statement.  Selective acceptance is a cross-fitted risk decision and
is allowed to return ``predicted_qualified`` only after all training gates
pass.  A failed gate is represented as a controlled negative; it never creates
a model lock or unlocks a FEM run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from ..folds import FOLD_SEED, folds
from .dataset import load_training_dataset, verify_immutable_package
from .m4e import _aggregate, _latent
from .m4e2 import (
    M4E2_CANDIDATE_SPECS,
    M4E2_WEIGHTS,
    _geometry_support,
    _labels_and_signature,
    _pool_model_predictions,
)
from .models import analytic_power_carrying_mask, angle_features, cutoff_identity, region_masks


DATASET_ID = "task004_angle_nominal_p5_ny4_train112_v1"
FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
TARGETS = ("R_total", "T_total", "A_balance")
P1 = "L1_local_rbf_k24_s1e-08"
P2 = "L2_local_matern_k24"
P3 = "E1_latent_median_ensemble"
PREDICTORS = (P1, P2, P3)
RULES = ("S1_pre_frozen_m4e2_ensemble", "S2_std_disagreement_max")
OOF_CANDIDATES = (P1, P2, "L2_local_matern_k32", P3)
QUANTILE_GRID = (0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
MIN_ACCEPTED_OOF = 0.70
MIN_ACCEPTED_POOL = 0.70
MIN_ACCEPTED_BLIND = 12


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                         allow_nan=False).encode()).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _signature(mask: np.ndarray) -> str:
    return ";".join(str(int(value)) for value in np.flatnonzero(mask))


def _metrics(truth: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    truth = np.asarray(truth, dtype=np.float64)
    prediction = np.asarray(prediction, dtype=np.float64)
    if truth.size == 0:
        return {"n": 0, "nrmse": float("inf"), "p95_abs": float("inf"),
                "max_abs": float("inf")}
    error = prediction - truth
    scale = float(np.ptp(truth)) or 1.0
    return {"n": int(error.size),
            "nrmse": float(np.sqrt(np.mean(error ** 2)) / scale),
            "p95_abs": float(np.percentile(np.abs(error), 95)),
            "max_abs": float(np.max(np.abs(error)))}


def _metrics_all(truth: np.ndarray, prediction: np.ndarray,
                 indices: np.ndarray) -> dict[str, dict[str, Any]]:
    return {target: _metrics(truth[indices, i], prediction[indices, i])
            for i, target in enumerate(TARGETS)}


def _composition_exact(prediction: np.ndarray, atol: float = 1.0e-12) -> bool:
    values = np.asarray(prediction, dtype=np.float64)
    return bool(np.max(np.abs(np.sum(values, axis=1) - 1.0)) <= atol and
                np.min(values) >= -atol)


def _boundary_flags(angles: np.ndarray) -> np.ndarray:
    values = np.asarray(angles, dtype=np.float64)
    return ((np.isclose(values[:, 0], 0.5, atol=1.0e-10) |
             np.isclose(values[:, 0], 10.0, atol=1.0e-10) |
             np.isclose(values[:, 1], 0.0, atol=1.0e-10) |
             np.isclose(values[:, 1], 90.0, atol=1.0e-10)))


def _load_oof(path: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    payload = json.loads(path.read_text())
    if payload.get("dataset_id") != DATASET_ID or payload.get("validation_target_accessed") is not False:
        raise ValueError("M4H OOF identity or validation guard failed")
    records = payload.get("records", {})
    for name in OOF_CANDIDATES:
        if len(records.get(name, [])) != 112:
            raise ValueError(f"M4H needs 112 OOF rows for {name}")
    return records, payload


def _rows(records: dict[str, list[dict[str, Any]]], name: str) -> dict[str, np.ndarray]:
    values = records[name]
    return {
        "angles": np.asarray([row["angle"] for row in values], dtype=np.float64),
        "truth": np.asarray([row["truth"] for row in values], dtype=np.float64),
        "prediction": np.asarray([row["prediction"] for row in values], dtype=np.float64),
        "std": np.asarray([row["std"] for row in values], dtype=np.float64),
        "error": np.asarray([row["error"] for row in values], dtype=np.float64),
        "fold": np.asarray([row["fold"] for row in values], dtype=np.int64),
        "margin": np.asarray([row["signed_cutoff_margin"] for row in values], dtype=np.float64),
        "mask_signature": np.asarray([row["mask_signature"] for row in values], dtype=object),
    }


def _fold_data(folds_path: Path, angles: np.ndarray,
               masks: np.ndarray) -> tuple[list[tuple[np.ndarray, np.ndarray]], dict[str, Any]]:
    payload = json.loads(folds_path.read_text())
    if payload.get("training_count") != 112 or payload.get("fold_seed") != FOLD_SEED:
        raise ValueError("unexpected immutable train112 folds")
    split = []
    fold_for = np.full(112, -1, dtype=np.int64)
    for item in payload.get("folds", []):
        fold = int(item["fold"])
        train = np.asarray(item["train_indices"], dtype=np.int64)
        test = np.asarray(item["test_indices"], dtype=np.int64)
        split.append((train, test))
        fold_for[test] = fold
    if len(split) != 5 or not np.array_equal(np.sort(np.concatenate([x[1] for x in split])), np.arange(112)):
        raise ValueError("train112 outer folds do not cover every index exactly once")
    if not np.all(fold_for >= 0):
        raise ValueError("train112 fold assignment is incomplete")
    for fold, (train, test) in enumerate(split):
        expected = [_signature(masks[i]) for i in train]
        if len(set(train.tolist()) & set(test.tolist())):
            raise ValueError(f"fold {fold} has train/test overlap")
        if payload["folds"][fold].get("fold_sha256") != canonical_hash({
                "fold": fold, "train_indices": train.tolist(),
                "test_indices": test.tolist(),
                "test_tuples": payload["folds"][fold]["test_tuples"]}):
            raise ValueError(f"fold {fold} hash mismatch")
        del expected
    return split, {"fold_for_index": fold_for, "payload": payload}


def _quantile_bounds(values: np.ndarray) -> tuple[float, float]:
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return (0.0, 1.0)
    low, high = float(np.percentile(values, 5)), float(np.percentile(values, 95))
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        high = low + 1.0
    return low, high


def _scale(values: np.ndarray, bounds: tuple[float, float]) -> np.ndarray:
    low, high = bounds
    return np.clip((np.asarray(values, dtype=np.float64) - low) / max(high - low, 1.0e-15), 0.0, 1.0)


def _component_raw(angles: np.ndarray, records: dict[str, list[dict[str, Any]]],
                  *, fold_train: list[np.ndarray] | None,
                  train_angles: np.ndarray | None,
                  train_masks: np.ndarray | None) -> dict[str, np.ndarray]:
    """Build only allowed response-predictor/geometry risk signals.

    ``fold_train`` is present for OOF rows and gives each row its own outer
    training topology support.  For response-blind designs it is absent and
    the full train112 package is the authority.
    """
    p1 = _rows(records, P1)
    p2 = _rows(records, P2)
    p2k32 = _rows(records, "L2_local_matern_k32")
    n = len(angles)
    std = p2["std"].copy()
    d12 = np.abs(p1["prediction"] - p2["prediction"])
    d23 = np.abs(p2["prediction"] - p2k32["prediction"])
    if fold_train is None:
        query_x = angle_features(angles, "F1")
        train_x = angle_features(np.asarray(train_angles), "F1")
        distance = np.min(np.linalg.norm(query_x[:, None, :] - train_x[None, :, :], axis=2), axis=1)
        masks = analytic_power_carrying_mask(angles)
        signatures = [_signature(mask) for mask in masks]
        train_signatures = [_signature(mask) for mask in np.asarray(train_masks)]
        train_counts = {sig: train_signatures.count(sig) for sig in set(train_signatures)}
        topology_supported = np.asarray([sig in train_counts for sig in signatures], dtype=bool)
        topology_risk = np.asarray([1.0 if sig not in train_counts else
                                    1.0 / np.sqrt(max(train_counts[sig], 1))
                                    for sig in signatures], dtype=np.float64)
    else:
        masks = analytic_power_carrying_mask(angles)
        signatures = [_signature(mask) for mask in masks]
        distance = np.empty(n, dtype=np.float64)
        topology_supported = np.empty(n, dtype=bool)
        topology_risk = np.empty(n, dtype=np.float64)
        for i in range(n):
            train = np.asarray(fold_train[i], dtype=np.int64)
            train_x = angle_features(angles[train], "F1")
            query_x = angle_features(angles[i:i + 1], "F1")
            distance[i] = float(np.min(np.linalg.norm(train_x - query_x, axis=1)))
            train_signatures = [_signature(masks[j]) for j in train]
            count = train_signatures.count(signatures[i])
            topology_supported[i] = count > 0
            topology_risk[i] = 1.0 if count == 0 else 1.0 / np.sqrt(count)
    _, margin = cutoff_identity(angles)
    cutoff_risk = 1.0 / (np.abs(margin) + 0.005)
    boundary = _boundary_flags(angles).astype(np.float64)
    low = (angles[:, 0] <= 2.0).astype(np.float64)
    high = (angles[:, 1] >= 75.0).astype(np.float64)
    return {"native_std": std, "rbf_matern_disagreement": d12,
            "matern_k24_k32_disagreement": d23,
            "nearest_training_distance": distance,
            "cutoff_risk": cutoff_risk, "topology_risk": topology_risk,
            "boundary_risk": boundary, "low_grazing_flag": low,
            "high_azimuth_flag": high, "topology_supported": topology_supported,
            "mask_signature": np.asarray(signatures, dtype=object),
            "cutoff_margin": np.asarray(margin, dtype=np.float64)}


def _fit_bounds(raw: dict[str, np.ndarray], source: np.ndarray) -> dict[str, Any]:
    bounds: dict[str, Any] = {}
    for name in ("native_std", "rbf_matern_disagreement", "matern_k24_k32_disagreement",
                 "nearest_training_distance", "cutoff_risk", "topology_risk"):
        values = np.asarray(raw[name])
        if values.ndim == 1:
            bounds[name] = list(_quantile_bounds(values[source]))
        else:
            bounds[name] = [list(_quantile_bounds(values[source, i])) for i in range(values.shape[1])]
    return bounds


def _scale_with_bounds(values: np.ndarray, bound: Any) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    if values.ndim == 1:
        return _scale(values, (float(bound[0]), float(bound[1])))
    return np.column_stack([_scale(values[:, i], (float(bound[i][0]), float(bound[i][1])))
                            for i in range(values.shape[1])])


def _risk_from_raw(raw: dict[str, np.ndarray], bounds: dict[str, Any], rule: str) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    std = _scale_with_bounds(raw["native_std"], bounds["native_std"])
    d12 = _scale_with_bounds(raw["rbf_matern_disagreement"], bounds["rbf_matern_disagreement"])
    d23 = _scale_with_bounds(raw["matern_k24_k32_disagreement"], bounds["matern_k24_k32_disagreement"])
    distance = _scale_with_bounds(raw["nearest_training_distance"], bounds["nearest_training_distance"])
    cutoff = _scale_with_bounds(raw["cutoff_risk"], bounds["cutoff_risk"])
    topology = _scale_with_bounds(raw["topology_risk"], bounds["topology_risk"])
    # The M4E2 contract calls this term cutoff_topology_bonus.  It is a risk
    # term here: proximity to a cutoff or rare/unseen topology increases risk.
    geometry = np.clip(0.5 * cutoff[:, None] + 0.35 * topology[:, None] +
                       0.15 * raw["boundary_risk"][:, None], 0.0, 1.0)
    if rule == RULES[0]:
        target_risk = (M4E2_WEIGHTS["native_std"] * std +
                       M4E2_WEIGHTS["matern_k24_k32_disagreement"] * d23 +
                       M4E2_WEIGHTS["rbf_matern_disagreement"] * d12 +
                       M4E2_WEIGHTS["nearest_training_distance"] * distance[:, None] +
                       M4E2_WEIGHTS["cutoff_topology_bonus"] * geometry)
    elif rule == RULES[1]:
        disagreement = np.maximum(d12, d23)
        target_risk = np.maximum(np.max(std, axis=1)[:, None],
                                 np.max(disagreement, axis=1)[:, None])
        target_risk = np.broadcast_to(target_risk, (len(target_risk), 3)).copy()
    else:
        raise ValueError(f"unknown selective risk rule {rule}")
    components = {"native_std_scaled": std, "rbf_matern_disagreement_scaled": d12,
                  "matern_k24_k32_disagreement_scaled": d23,
                  "nearest_training_distance_scaled": np.broadcast_to(distance[:, None], (len(distance), 3)),
                  "cutoff_topology_scaled": geometry,
                  "target_risk": target_risk,
                  "risk_score": np.max(target_risk, axis=1)}
    return np.asarray(components["risk_score"], dtype=np.float64), components


def _coverage(truth: np.ndarray, prediction: np.ndarray, std: np.ndarray,
              indices: np.ndarray) -> dict[str, float]:
    if len(indices) == 0:
        return {target: 0.0 for target in TARGETS}
    values = np.abs(prediction[indices] - truth[indices]) <= 1.96 * np.maximum(std[indices], 1.0e-12)
    return {target: float(np.mean(values[:, i])) for i, target in enumerate(TARGETS)}


def _supported_indices(windows_path: Path) -> dict[str, np.ndarray]:
    payload = json.loads(windows_path.read_text())
    result = {}
    for item in payload.get("windows", []):
        result[item["name"]] = np.asarray([
            int(row["index"]) for row in item.get("support_rows", [])
            if row.get("classification") != "unsupported_extrapolation"
        ], dtype=np.int64)
    return result


def _window_report(truth: np.ndarray, prediction: np.ndarray, accepted: np.ndarray,
                   windows_path: Path) -> tuple[dict[str, Any], bool]:
    output: dict[str, Any] = {}
    gates = []
    for name, indices in _supported_indices(windows_path).items():
        selected = np.asarray(sorted(set(indices.tolist()) & set(np.flatnonzero(accepted).tolist())), dtype=np.int64)
        metrics = _metrics_all(truth, prediction, selected) if len(selected) else {}
        gate = bool(len(selected) > 0 and all(item["p95_abs"] <= 0.02 for item in metrics.values()))
        gates.append(gate)
        output[name] = {"supported_indices": indices.tolist(), "accepted_indices": selected.tolist(),
                        "accepted_count": int(len(selected)), "metrics": metrics, "gate": gate}
    return output, bool(all(gates) if gates else False)


def _region_report(angles: np.ndarray, truth: np.ndarray, prediction: np.ndarray,
                   std: np.ndarray, accepted: np.ndarray) -> dict[str, Any]:
    masks = region_masks(angles)
    masks = dict(masks)
    masks["boundary"] = _boundary_flags(angles)
    masks["old96"] = np.arange(len(angles)) < 96
    masks["new16"] = np.arange(len(angles)) >= 96
    result = {}
    for name, mask in masks.items():
        all_idx = np.flatnonzero(mask)
        accepted_idx = np.flatnonzero(mask & accepted)
        result[name] = {
            "total_count": int(len(all_idx)), "accepted_count": int(len(accepted_idx)),
            "acceptance_rate": float(len(accepted_idx) / len(all_idx)) if len(all_idx) else 0.0,
            "metrics_accepted": _metrics_all(truth, prediction, accepted_idx) if len(accepted_idx) else {},
            "coverage_accepted": _coverage(truth, prediction, std, accepted_idx),
        }
    return result


def _source_threshold(source: np.ndarray, risk: np.ndarray, truth: np.ndarray,
                      prediction: np.ndarray, std: np.ndarray,
                      supported_windows: Path, quantiles: Iterable[float]) -> dict[str, Any]:
    """Choose a threshold using only other folds' OOF rows.

    A threshold candidate is first checked against the source rows.  The
    highest-coverage source candidate that meets the same hard accuracy,
    support and interval contracts is selected.  If none meets the contract,
    q=0.70 is selected and the fold records that this was a controlled source
    failure; held-out rows are never used to repair the choice.
    """
    source = np.asarray(source, dtype=np.int64)
    candidates = []
    for q in quantiles:
        threshold = float(np.quantile(risk[source], q, method="linear"))
        accepted = risk <= threshold + 1.0e-15
        idx = np.asarray(sorted(set(source.tolist()) & set(np.flatnonzero(accepted).tolist())), dtype=np.int64)
        metrics = _metrics_all(truth, prediction, idx) if len(idx) else {}
        windows, supported_gate = _window_report(truth, prediction, accepted & np.isin(np.arange(len(risk)), source), supported_windows)
        coverage = _coverage(truth, prediction, std, idx)
        accuracy_gate = bool(len(idx) and all(item["nrmse"] <= 0.01 and item["p95_abs"] <= 0.01 and
                                             item["max_abs"] <= 0.03 for item in metrics.values()))
        coverage_gate = bool(len(idx) and all(0.90 <= value <= 0.99 for value in coverage.values()))
        composition_gate = _composition_exact(prediction[idx]) if len(idx) else False
        source_gate = bool(accuracy_gate and supported_gate and coverage_gate and composition_gate and
                           len(idx) / len(source) >= MIN_ACCEPTED_OOF)
        candidates.append({"quantile": float(q), "threshold": threshold, "accepted_count": int(len(idx)),
                           "accepted_fraction": float(len(idx) / len(source)), "metrics": metrics,
                           "coverage": coverage, "accuracy_gate": accuracy_gate,
                           "supported_window_gate": supported_gate, "coverage_gate": coverage_gate,
                           "composition_gate": composition_gate, "source_gate": source_gate,
                           "windows": windows})
    passing = [item for item in candidates if item["source_gate"]]
    if passing:
        selected = min(passing, key=lambda item: (item["quantile"], item["threshold"]))
        fallback = False
    else:
        selected = next(item for item in candidates if abs(item["quantile"] - 0.70) < 1.0e-12)
        fallback = True
    selected = dict(selected)
    selected["source_gate_selection_failed"] = fallback
    selected["candidate_grid"] = candidates
    return selected


def _risk_for_rows(raw: dict[str, np.ndarray], source: np.ndarray,
                   truth: np.ndarray, prediction: np.ndarray, std: np.ndarray,
                   rule: str, windows_path: Path) -> dict[str, Any]:
    bounds = _fit_bounds(raw, source)
    risk, components = _risk_from_raw(raw, bounds, rule)
    threshold = _source_threshold(source, risk, truth, prediction, std, windows_path, QUANTILE_GRID)
    return {"bounds": bounds, "risk": risk, "components": components, "threshold": threshold}


def _oof_selective(*, records: dict[str, list[dict[str, Any]]], angles: np.ndarray,
                   truth: np.ndarray, masks: np.ndarray, split: list[tuple[np.ndarray, np.ndarray]],
                   windows_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    values = {name: _rows(records, name) for name in OOF_CANDIDATES}
    fold_train = [None] * len(angles)
    for train, test in split:
        for index in test:
            fold_train[int(index)] = train
    raw = _component_raw(angles, records, fold_train=fold_train,
                         train_angles=None, train_masks=None)
    fold_thresholds: dict[str, Any] = {}
    final: dict[str, Any] = {}
    selective_records: dict[str, list[dict[str, Any]]] = {}
    for rule in RULES:
        fold_rows = []
        accepted_by_predictor = {name: np.zeros(len(angles), dtype=bool) for name in PREDICTORS}
        risk_by_fold = np.full(len(angles), np.nan)
        component_by_fold: dict[str, np.ndarray] = {}
        for fold, (_, test) in enumerate(split):
            source = np.asarray(sorted(set(range(len(angles))) - set(test.tolist())), dtype=np.int64)
            fit = _risk_for_rows(raw, source, truth, values[P2]["prediction"], values[P2]["std"], rule, windows_path)
            risk_by_fold[test] = fit["risk"][test]
            for key, array in fit["components"].items():
                if key not in component_by_fold:
                    shape = (len(angles),) if array.ndim == 1 else (len(angles), array.shape[1])
                    component_by_fold[key] = np.full(shape, np.nan, dtype=np.float64)
                component_by_fold[key][test] = array[test]
            threshold = float(fit["threshold"]["threshold"])
            for predictor in PREDICTORS:
                accepted_by_predictor[predictor][test] = risk_by_fold[test] <= threshold + 1.0e-15
            fold_rows.append({"fold": fold, "test_indices": test.tolist(),
                              "source_outer_folds": [k for k in range(len(split)) if k != fold],
                              "source_indices": source.tolist(),
                              "normalization_bounds": fit["bounds"],
                              "threshold": fit["threshold"],
                              "held_out_response_used_for_threshold": False})
        fold_thresholds[rule] = fold_rows
        for predictor in PREDICTORS:
            pred = values[predictor]["prediction"]
            std = values[predictor]["std"]
            accepted = accepted_by_predictor[predictor]
            accepted_idx = np.flatnonzero(accepted)
            metrics = _metrics_all(truth, pred, accepted_idx) if len(accepted_idx) else {}
            coverage = _coverage(truth, pred, std, accepted_idx)
            windows, window_gate = _window_report(truth, pred, accepted, windows_path)
            comp_gate = _composition_exact(pred[accepted_idx]) if len(accepted_idx) else False
            accuracy_gate = bool(len(accepted_idx) >= 1 and all(
                item["nrmse"] <= 0.01 and item["p95_abs"] <= 0.01 and item["max_abs"] <= 0.03
                for item in metrics.values()))
            coverage_gate = bool(len(accepted_idx) >= 1 and all(0.90 <= item <= 0.99 for item in coverage.values()))
            rows = []
            for index in range(len(angles)):
                fold = int(values[P2]["fold"][index])
                fold_item = fold_rows[fold]
                reason = "accepted_training_risk" if accepted[index] else "requires_fem_risk_gate"
                row = {
                    "sample_index": index, "angle": angles[index].round(12).tolist(),
                    "identity": "old96" if index < 96 else "new16", "fold": fold,
                    "predictor": predictor, "risk_rule": rule,
                    "truth": truth[index].tolist(), "prediction": pred[index].tolist(),
                    "std": std[index].tolist(), "error": (pred[index] - truth[index]).tolist(),
                    "absolute_error": np.abs(pred[index] - truth[index]).tolist(),
                    "risk_score": float(risk_by_fold[index]),
                    "risk_components": {key: (value[index].tolist() if np.ndim(value[index]) else float(value[index]))
                                        for key, value in component_by_fold.items()},
                    "threshold": float(fold_item["threshold"]["threshold"]),
                    "threshold_quantile": float(fold_item["threshold"]["quantile"]),
                    "threshold_source_folds": fold_item["source_outer_folds"],
                    "threshold_source_indices_hash": canonical_hash(fold_item["source_indices"]),
                    "accepted": bool(accepted[index]), "reason": reason,
                    "cutoff_margin": float(raw["cutoff_margin"][index]),
                    "mask_signature": str(raw["mask_signature"][index]),
                    "topology_supported_in_outer_train": bool(raw["topology_supported"][index]),
                    "region_labels": [name for name, values_ in region_masks(angles).items() if bool(values_[index])],
                    "boundary": bool(_boundary_flags(angles)[index]),
                    "response_used_for_acceptance": False,
                }
                rows.append(row)
            selective_records[f"{predictor}::{rule}"] = rows
            final[f"{predictor}::{rule}"] = {
                "predictor": predictor, "risk_rule": rule,
                "accepted_indices": accepted_idx.astype(int).tolist(),
                "rejected_indices": np.flatnonzero(~accepted).astype(int).tolist(),
                "accepted_indices_sha256": canonical_hash(accepted_idx.astype(int).tolist()),
                "rejected_indices_sha256": canonical_hash(np.flatnonzero(~accepted).astype(int).tolist()),
                "accepted_angle_tuple_sha256": canonical_hash(angles[accepted_idx].round(12).tolist()),
                "accepted_count": int(len(accepted_idx)),
                "accepted_fraction": float(len(accepted_idx) / len(angles)),
                "metrics_accepted": metrics, "coverage_accepted": coverage,
                "supported_window_metrics": windows,
                "accepted_accuracy_gate": accuracy_gate,
                "accepted_supported_window_gate": window_gate,
                "accepted_coverage_gate": coverage_gate,
                "accepted_composition_gate": comp_gate,
                "crossfit_threshold_gate": bool(all(not item["held_out_response_used_for_threshold"]
                                                    for item in fold_rows)),
                "region_report": _region_report(angles, truth, pred, std, accepted),
            }
    return {"rules": fold_thresholds, "results": final}, selective_records


def _full_train_records(angles: np.ndarray, aggregates: np.ndarray, masks: np.ndarray,
                        p1: np.ndarray, p2: np.ndarray, p2k32: np.ndarray,
                        p2std: np.ndarray) -> dict[str, list[dict[str, Any]]]:
    """Adapt full-train response-blind predictions to the component builder."""
    out: dict[str, list[dict[str, Any]]] = {}
    for name, prediction, std in ((P1, p1, np.maximum(p2std, 1.0e-12)),
                                  (P2, p2, p2std), ("L2_local_matern_k32", p2k32, p2std),
                                  (P3, _aggregate(np.median(np.stack([_latent(p1), _latent(p2), _latent(p2k32)], axis=2), axis=2)), p2std)):
        out[name] = []
        for i in range(len(angles)):
            out[name].append({"angle": angles[i].tolist(), "truth": aggregates[i, :3].tolist(),
                              "prediction": prediction[i].tolist(), "std": std[i].tolist(),
                              "error": [0.0, 0.0, 0.0], "fold": 0,
                              "signed_cutoff_margin": float(cutoff_identity(angles)[1][i]),
                              "mask_signature": _signature(masks[i])})
    return out


def _screen_design(angles: np.ndarray, train_angles: np.ndarray, train_aggregates: np.ndarray,
                   train_masks: np.ndarray, final_bounds: dict[str, Any],
                   final_thresholds: dict[str, float], design_name: str) -> dict[str, Any]:
    specs = {spec["candidate"]: spec for spec in M4E2_CANDIDATE_SPECS}
    p1, _ = _pool_model_predictions(specs[P1], train_angles, train_aggregates, angles)
    p2, p2std = _pool_model_predictions(specs[P2], train_angles, train_aggregates, angles)
    p2k32, _ = _pool_model_predictions(specs["L2_local_matern_k32"], train_angles, train_aggregates, angles)
    latent = np.median(np.stack([_latent(p1), _latent(p2), _latent(p2k32)], axis=2), axis=2)
    p3 = _aggregate(latent)
    # The component helper accepts prediction records for the actual query.
    zeros = np.zeros((len(angles), 3), dtype=np.float64)
    records = _full_train_records(angles, zeros, analytic_power_carrying_mask(angles), p1, p2, p2k32, p2std)
    raw = _component_raw(angles, records, fold_train=None,
                         train_angles=train_angles, train_masks=train_masks)
    result: dict[str, Any] = {"design_name": design_name,
                              "point_count": int(len(angles)), "points": angles.round(12).tolist(),
                              "predictor_screening": {}, "validation_response_accessed": False}
    for rule in RULES:
        risk, components = _risk_from_raw(raw, final_bounds[rule], rule)
        for predictor, pred in ((P1, p1), (P2, p2), (P3, p3)):
            threshold = float(final_thresholds[f"{predictor}::{rule}"])
            accepted = risk <= threshold + 1.0e-15
            key = f"{predictor}::{rule}"
            result["predictor_screening"][key] = {
                "risk_rule": rule, "threshold": threshold,
                "risk_score": risk.tolist(),
                "accepted_indices": np.flatnonzero(accepted).astype(int).tolist(),
                "rejected_indices": np.flatnonzero(~accepted).astype(int).tolist(),
                "accepted_indices_sha256": canonical_hash(np.flatnonzero(accepted).astype(int).tolist()),
                "rejected_indices_sha256": canonical_hash(np.flatnonzero(~accepted).astype(int).tolist()),
                "accepted_angle_tuple_sha256": canonical_hash(angles[accepted].round(12).tolist()),
                "accepted_count": int(np.sum(accepted)),
                "accepted_fraction": float(np.mean(accepted)) if len(accepted) else 0.0,
                "risk_summary": {
                    "min": float(np.min(risk)), "p50": float(np.percentile(risk, 50)),
                    "p95": float(np.percentile(risk, 95)), "max": float(np.max(risk)),
                },
                "response_used_for_acceptance": False,
            }
    return result


def _structural_domain(pool_angles: np.ndarray, blind_angles: np.ndarray,
                       train_angles: np.ndarray, train_masks: np.ndarray,
                       train_tuple_hash: str, implementation_sha: str) -> dict[str, Any]:
    train_x = angle_features(train_angles, "F1")
    loo = []
    for i in range(len(train_x)):
        distances = np.linalg.norm(train_x - train_x[i], axis=1)
        distances[i] = np.inf
        loo.append(float(np.min(distances)))
    distance_threshold = float(np.percentile(loo, 95))
    train_signatures = {_signature(row) for row in train_masks}
    train_counts = {sig: sum(_signature(row) == sig for row in train_masks) for sig in train_signatures}

    def classify(angles: np.ndarray) -> list[dict[str, Any]]:
        mask = analytic_power_carrying_mask(angles)
        feature = angle_features(angles, "F1")
        rows = []
        for i, point in enumerate(angles):
            distance = float(np.min(np.linalg.norm(train_x - feature[i], axis=1)))
            sig = _signature(mask[i])
            geometry_full = _geometry_support(point, train_angles)
            geometry = {key: geometry_full[key] for key in
                        ("classification", "convex_hull_contains", "direction_sector_count",
                         "boundary_edges", "local_rank")}
            topology = sig in train_signatures
            support = bool(topology and distance <= distance_threshold and
                           geometry["classification"] != "unsupported_extrapolation")
            rows.append({"index": i, "angle": point.round(12).tolist(),
                         "nearest_training_distance": distance,
                         "distance_threshold_leave_one_out_p95": distance_threshold,
                         "mask_signature": sig, "topology_supported": topology,
                         "topology_count": int(train_counts.get(sig, 0)),
                         "geometry_support": geometry, "structural_supported": support})
        return rows
    pool = classify(pool_angles); blind = classify(blind_angles)
    return {
        "schema_version": "task004.angle-aggregate-structural-support-domain.v1",
        "dataset_id": DATASET_ID, "forward_solver_sha": FORWARD_SHA,
        "surrogate_training_code_sha": implementation_sha,
        "training_tuple_sha256": train_tuple_hash, "response_blind": True,
        "support_contract": {
            "topology": "analytic mask signature must occur in train112",
            "distance": "query F1 distance <= train112 leave-one-out nearest-neighbour p95",
            "geometry": "interior bracketed or boundary one-sided supported",
            "order_semantics": "structural aggregate support does not qualify order outputs",
        },
        "training_loo_distance_values": loo,
        "distance_threshold": distance_threshold,
        "candidate_pool": {"count": len(pool), "supported_count": int(sum(row["structural_supported"] for row in pool)),
                            "supported_indices": [row["index"] for row in pool if row["structural_supported"]],
                            "rows": pool},
        "blind_design": {"count": len(blind), "supported_count": int(sum(row["structural_supported"] for row in blind)),
                          "supported_indices": [row["index"] for row in blind if row["structural_supported"]],
                          "rows": blind},
        "validation_response_accessed": False,
    }


def run_m4h(*, dataset_dir: Path, output_dir: Path, folds_path: Path,
            oof_path: Path, windows_path: Path, candidate_pool_path: Path,
            blind_design_path: Path, implementation_sha: str) -> dict[str, Any]:
    manifest = verify_immutable_package(dataset_dir, expected_dataset_id=DATASET_ID)
    data = load_training_dataset(dataset_dir)
    angles = np.asarray(data["angles.npy"], dtype=np.float64)
    aggregates = np.asarray(data["aggregates.npy"], dtype=np.float64)[:, :3]
    masks = np.asarray(data["power_carrying_mask.npy"], dtype=bool)
    if manifest.get("forward_solver_sha") != FORWARD_SHA or manifest.get("validation_target_accessed") is not False:
        raise ValueError("train112 manifest is not the approved immutable package")
    records, oof_payload = _load_oof(oof_path)
    split, fold_meta = _fold_data(folds_path, angles, masks)
    truth = np.asarray([row["truth"] for row in records[P2]], dtype=np.float64)
    selective, selective_records = _oof_selective(records=records, angles=angles, truth=truth,
                                                  masks=masks, split=split, windows_path=windows_path)

    # Final production screening normalization is fitted from all training OOF
    # risk rows, while each OOF decision above remains strictly cross-fitted.
    fold_train = [None] * len(angles)
    for train, test in split:
        for index in test:
            fold_train[int(index)] = train
    raw_oof = _component_raw(angles, records, fold_train=fold_train,
                             train_angles=None, train_masks=None)
    final_bounds: dict[str, Any] = {}
    final_thresholds: dict[str, float] = {}
    for rule in RULES:
        bounds = _fit_bounds(raw_oof, np.arange(len(angles), dtype=np.int64))
        final_bounds[rule] = bounds
        for predictor in PREDICTORS:
            values = selective["results"][f"{predictor}::{rule}"]
            thresholds = [float(row["threshold"]["threshold"])
                          for row in selective["rules"][rule]]
            final_thresholds[f"{predictor}::{rule}"] = float(np.median(thresholds))
            values["final_threshold_for_response_blind_screening"] = final_thresholds[f"{predictor}::{rule}"]

    pool_payload = json.loads(candidate_pool_path.read_text())
    pool_angles = np.asarray([[float(item["grazing_deg"]), float(item["azimuth_deg"])]
                              for item in pool_payload["points"]], dtype=np.float64)
    blind_payload = json.loads(blind_design_path.read_text())
    blind_angles = np.asarray([[float(item["grazing_deg"]), float(item["azimuth_deg"])]
                               for item in blind_payload["points"]], dtype=np.float64)
    pool_screen = _screen_design(pool_angles, angles, aggregates, masks, final_bounds,
                                 final_thresholds, "candidate_pool_4096")
    blind_screen = _screen_design(blind_angles, angles, aggregates, masks, final_bounds,
                                  final_thresholds, "blind_design_24")
    structural = _structural_domain(pool_angles, blind_angles, angles, masks,
                                    manifest["training_tuple_sha256"], implementation_sha)
    acceptance = {
        "schema_version": "task004.angle-aggregate-selective-acceptance-domain.v1",
        "dataset_id": DATASET_ID, "forward_solver_sha": FORWARD_SHA,
        "surrogate_training_code_sha": implementation_sha,
        "training_tuple_sha256": manifest["training_tuple_sha256"], "response_blind": True,
        "candidate_pool_design_id": pool_payload.get("design_id"),
        "candidate_pool_tuple_sha256": pool_payload.get("point_tuple_sha256"),
        "blind_design_id": blind_payload.get("design_id"),
        "blind_tuple_sha256": blind_payload.get("point_tuple_sha256"),
        "candidate_pool": pool_screen["predictor_screening"],
        "blind_design": blind_screen["predictor_screening"],
        "validation_response_accessed": False,
    }
    comparisons = {}
    for key, result in selective["results"].items():
        screen_pool = pool_screen["predictor_screening"][key]
        screen_blind = blind_screen["predictor_screening"][key]
        accepted_pool = screen_pool["accepted_count"] / len(pool_angles)
        accepted_blind = screen_blind["accepted_count"]
        gates = {
            "accepted_oof_fraction": result["accepted_fraction"] >= MIN_ACCEPTED_OOF,
            "accepted_candidate_pool_fraction": accepted_pool >= MIN_ACCEPTED_POOL,
            "accepted_blind_count": accepted_blind >= MIN_ACCEPTED_BLIND,
            "accepted_accuracy": result["accepted_accuracy_gate"],
            "accepted_supported_window_accuracy": result["accepted_supported_window_gate"],
            "accepted_cross_fitted_coverage": result["accepted_coverage_gate"],
            "accepted_composition": result["accepted_composition_gate"],
            "crossfit_thresholds": result["crossfit_threshold_gate"],
        }
        comparisons[key] = {**result,
                           "candidate_pool_accepted_count": screen_pool["accepted_count"],
                           "candidate_pool_accepted_fraction": accepted_pool,
                           "blind_design_accepted_count": accepted_blind,
                           "blind_design_accepted_indices": screen_blind["accepted_indices"],
                           "gates": gates, "all_selective_gates": bool(all(gates.values()))}
    qualified = any(item["all_selective_gates"] for item in comparisons.values())
    output_dir.mkdir(parents=True, exist_ok=True)
    contract = {
        "schema_version": "task004.angle-aggregate-selective-qualification-contract.v1",
        "dataset_id": DATASET_ID, "forward_solver_sha": FORWARD_SHA,
        "surrogate_training_code_sha": implementation_sha,
        "training_tuple_sha256": manifest["training_tuple_sha256"],
        "point_predictors": [P1, P2, P3], "risk_rules": list(RULES),
        "aggregate_only": True, "order_resolved_qualified": False,
        "minimums": {"accepted_oof_fraction": MIN_ACCEPTED_OOF,
                      "accepted_candidate_pool_fraction": MIN_ACCEPTED_POOL,
                      "accepted_blind_count": MIN_ACCEPTED_BLIND},
        "qualified": qualified,
        "controlled_negative": not qualified,
        "model_lock_created": False,
        "blind_fem_authorized": False,
        "validation_response_accessed": False,
        "failure_rule": "if no predictor/rule passes all gates, stop controlled-negative and require FEM on rejected points",
    }
    risk_contract = {
        "schema_version": "task004.angle-selective-risk-signal-contract.v1",
        "dataset_id": DATASET_ID, "forward_solver_sha": FORWARD_SHA,
        "surrogate_training_code_sha": implementation_sha,
        "allowed_signals": ["matern_k24_native_or_calibrated_std",
                            "rbf_vs_matern_k24_disagreement", "matern_k24_vs_k32_disagreement",
                            "nearest_training_distance", "signed_nearest_cutoff_margin",
                            "cutoff_order", "low_grazing_flag", "high_azimuth_flag",
                            "boundary_flag", "mask_signature_support"],
        "normalization": "per-outer-fold q05/q95 fitted only on other outer folds; final response-blind screen uses all-train OOF q05/q95",
        "rules": {
            RULES[0]: {"formula": "0.35*std + 0.25*matern_k24_k32 + 0.20*rbf_matern + 0.10*distance + 0.10*cutoff_topology",
                       "weights": M4E2_WEIGHTS, "cutoff_topology": "0.50 cutoff + 0.35 topology rarity/unsupported + 0.15 boundary"},
            RULES[1]: {"formula": "max(max_target(std), max_target(rbf_matern, matern_k24_k32))",
                       "uses_geometry": False},
        },
        "response_blind_screening": True, "validation_response_accessed": False,
    }
    crossfit = {
        "schema_version": "task004.angle-selective-risk-crossfit.v1",
        "dataset_id": DATASET_ID, "training_tuple_sha256": manifest["training_tuple_sha256"],
        "fold_seed": FOLD_SEED, "fold_identity": fold_meta["payload"]["fold_identity"],
        "rules": selective["rules"], "final_thresholds": final_thresholds,
        "final_normalization_bounds": final_bounds,
        "threshold_source_contract": "each outer-test threshold uses only the other four outer folds; held-out response excluded",
        "validation_response_accessed": False,
    }
    comparison_payload = {
        "schema_version": "task004.angle-selective-model-comparison.v1",
        "dataset_id": DATASET_ID, "forward_solver_sha": FORWARD_SHA,
        "surrogate_training_code_sha": implementation_sha,
        "training_tuple_sha256": manifest["training_tuple_sha256"],
        "candidate_set": list(PREDICTORS), "risk_rule_set": list(RULES),
        "results": comparisons, "qualified_pair": [key for key, value in comparisons.items()
                                                     if value["all_selective_gates"]],
        "model_lock_created": False, "validation_response_accessed": False,
    }
    (output_dir / "SELECTIVE_RISK_SIGNAL_CONTRACT.json").write_text(json.dumps(risk_contract, indent=2, sort_keys=True) + "\n")
    (output_dir / "SELECTIVE_RISK_CROSSFIT.json").write_text(json.dumps(crossfit, indent=2, sort_keys=True) + "\n")
    (output_dir / "SELECTIVE_MODEL_COMPARISON.json").write_text(json.dumps(comparison_payload, indent=2, sort_keys=True) + "\n")
    (output_dir / "SELECTIVE_OOF.json").write_text(json.dumps({
        "schema_version": "task004.angle-selective-oof.v1", "dataset_id": DATASET_ID,
        "records": selective_records, "validation_response_accessed": False}, indent=2, sort_keys=True) + "\n")
    (output_dir / "ANGLE_AGGREGATE_STRUCTURAL_SUPPORT_DOMAIN.json").write_text(json.dumps(structural, indent=2, sort_keys=True) + "\n")
    (output_dir / "ANGLE_AGGREGATE_SELECTIVE_ACCEPTANCE_DOMAIN.json").write_text(json.dumps(acceptance, indent=2, sort_keys=True) + "\n")
    (output_dir / "ANGLE_AGGREGATE_SELECTIVE_QUALIFICATION_CONTRACT.json").write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    return {"manifest": manifest, "comparison": comparison_payload, "contract": contract,
            "crossfit": crossfit, "structural": structural, "acceptance": acceptance,
            "selective_records": selective_records}
