"""Required M4I: final training-only selective threshold correction.

This module keeps only Q1 (local Matérn k24), Q2 (the existing latent median)
and the frozen S1 M4E2 risk rule.  It does not load validation responses or
launch a forward solver.  Thresholds are predictor-specific, source-fold
qualified and never fall back into a passing state.  Conditional intervals are
calibrated from accepted source OOF residuals only.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from ..folds import FOLD_SEED
from .dataset import load_training_dataset, verify_immutable_package
from .m4e import _aggregate
from .m4h import (
    DATASET_ID,
    FORWARD_SHA,
    P1,
    P2,
    P3,
    RULES,
    _composition_exact,
    _component_raw,
    _fit_bounds,
    _fold_data,
    _metrics_all,
    _risk_from_raw,
    _rows,
    _screen_design,
    _supported_indices,
    _window_report,
)


S1 = RULES[0]
S2 = RULES[1]
Q1 = P2
Q2 = P3
PREDICTORS = (Q1, Q2)
QUANTILES = (0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
MIN_ACCEPTED_FRACTION = 0.70
MIN_BLIND_ACCEPTED = 12
CONFORMAL_COVERAGE = 0.90
MAX_P95_HALF_WIDTH = 0.02
MAX_HALF_WIDTH = 0.03


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                         allow_nan=False).encode()).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _metrics(truth: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    if len(truth) == 0:
        return {"n": 0, "nrmse": float("inf"), "p95_abs": float("inf"), "max_abs": float("inf")}
    error = np.asarray(prediction, dtype=np.float64) - np.asarray(truth, dtype=np.float64)
    scale = float(np.ptp(truth)) or 1.0
    return {"n": int(error.size), "nrmse": float(np.sqrt(np.mean(error ** 2)) / scale),
            "p95_abs": float(np.percentile(np.abs(error), 95)),
            "max_abs": float(np.max(np.abs(error)))}


def _all_metrics(truth: np.ndarray, prediction: np.ndarray,
                 indices: np.ndarray) -> dict[str, dict[str, Any]]:
    return {target: _metrics(truth[indices, i], prediction[indices, i])
            for i, target in enumerate(("R_total", "T_total", "A_balance"))}


def _point_accuracy_gate(truth: np.ndarray, prediction: np.ndarray,
                         indices: np.ndarray) -> tuple[bool, dict[str, Any]]:
    metrics = _all_metrics(truth, prediction, indices)
    gate = bool(len(indices) > 0 and all(
        item["nrmse"] <= 0.01 and item["p95_abs"] <= 0.01 and item["max_abs"] <= 0.03
        for item in metrics.values()))
    return gate, metrics


def _point_error_score(metrics: dict[str, Any]) -> float:
    return float(max(max(item["nrmse"] / 0.01, item["p95_abs"] / 0.01,
                         item["max_abs"] / 0.03) for item in metrics.values()))


def _supported_gate_allow_empty(windows: dict[str, Any]) -> bool:
    """Check p95 only where the accepted set has supported points.

    An empty difficult window is not silently counted as zero error; it is
    retained in the report and the region acceptance audit.  The numerical
    p95 Gate is undefined for an empty subset, so it cannot by itself make a
    source threshold fail.
    """
    populated = [item for item in windows.values() if item["accepted_count"] > 0]
    return bool(populated and all(item["gate"] for item in populated))


def _source_threshold(source: np.ndarray, risk: np.ndarray, truth: np.ndarray,
                      prediction: np.ndarray, windows_path: Path) -> dict[str, Any]:
    """Select the highest-acceptance passing risk quantile from source rows."""
    source = np.asarray(source, dtype=np.int64)
    candidates: list[dict[str, Any]] = []
    for quantile in QUANTILES:
        threshold = float(np.quantile(risk[source], quantile, method="linear"))
        accepted = risk <= threshold + 1.0e-15
        accepted_source = np.asarray(sorted(set(source.tolist()) &
                                             set(np.flatnonzero(accepted).tolist())), dtype=np.int64)
        accuracy_gate, metrics = _point_accuracy_gate(truth, prediction, accepted_source)
        windows, _ = _window_report(
            truth, prediction, accepted & np.isin(np.arange(len(risk)), source), windows_path,
        )
        supported_gate = _supported_gate_allow_empty(windows)
        composition_gate = bool(len(accepted_source) > 0 and
                                _composition_exact(prediction[accepted_source]))
        fraction = float(len(accepted_source) / len(source))
        source_gate = bool(fraction >= MIN_ACCEPTED_FRACTION and accuracy_gate and
                           supported_gate and composition_gate)
        candidates.append({
            "quantile": float(quantile), "threshold": threshold,
            "accepted_indices": accepted_source.astype(int).tolist(),
            "accepted_count": int(len(accepted_source)), "accepted_fraction": fraction,
            "metrics": metrics, "point_error_score": _point_error_score(metrics),
            "accuracy_gate": accuracy_gate, "supported_window_gate": supported_gate,
            "composition_gate": composition_gate, "source_gate": source_gate,
            "windows": windows,
        })
    passing = [item for item in candidates if item["source_gate"]]
    if not passing:
        return {"status": "threshold_not_qualified", "source_gate_selection_failed": True,
                "selected": None, "candidate_grid": candidates}
    # Highest accepted fraction is the primary contract.  Error score and the
    # lower numerical threshold are deterministic tie-breakers only.
    selected = max(passing, key=lambda item: (
        item["accepted_fraction"], -item["point_error_score"], -item["threshold"],
        -item["quantile"],
    ))
    return {"status": "qualified", "source_gate_selection_failed": False,
            "selected": selected, "candidate_grid": candidates}


def _finite_conformal_quantile(values: np.ndarray, confidence: float = 0.95) -> float:
    values = np.sort(np.asarray(values, dtype=np.float64).reshape(-1))
    if len(values) == 0:
        return float("nan")
    # Finite-sample split-conformal upper order statistic.  ``higher`` keeps
    # the interval conservative without relying on a held-out response.
    level = min(1.0, math.ceil((len(values) + 1) * confidence) / len(values))
    return float(np.quantile(values, level, method="higher"))


def _conformal_report(truth: np.ndarray, prediction: np.ndarray, std: np.ndarray,
                      accepted: np.ndarray, radii: np.ndarray) -> dict[str, Any]:
    indices = np.flatnonzero(accepted)
    coverage_values = np.abs(prediction[indices] - truth[indices]) <= radii[indices]
    coverage = {target: float(np.mean(coverage_values[:, i])) if len(indices) else 0.0
                for i, target in enumerate(("R_total", "T_total", "A_balance"))}
    half_width = radii[indices] if len(indices) else np.empty((0, 3), dtype=float)
    sharpness = {}
    for i, target in enumerate(("R_total", "T_total", "A_balance")):
        values = half_width[:, i] if len(indices) else np.empty(0)
        sharpness[target] = {
            "p95_half_width": float(np.percentile(values, 95)) if len(values) else float("inf"),
            "max_half_width": float(np.max(values)) if len(values) else float("inf"),
            "min_half_width": float(np.min(values)) if len(values) else float("nan"),
            "finite_positive": bool(len(values) > 0 and np.isfinite(values).all() and np.all(values > 0.0)),
        }
    coverage_gate = bool(len(indices) > 0 and all(value >= CONFORMAL_COVERAGE for value in coverage.values()))
    sharpness_gate = bool(len(indices) > 0 and all(
        value["finite_positive"] and value["p95_half_width"] <= MAX_P95_HALF_WIDTH and
        value["max_half_width"] <= MAX_HALF_WIDTH for value in sharpness.values()))
    return {"accepted_count": int(len(indices)), "coverage": coverage,
            "coverage_gate": coverage_gate, "sharpness": sharpness,
            "sharpness_gate": sharpness_gate,
            "conservative_interval_warning": bool(any(value > 0.99 for value in coverage.values())),
            "old_upper_bound_is_not_a_gate": True}


def _predictor_rows(records: dict[str, list[dict[str, Any]]], name: str) -> dict[str, np.ndarray]:
    values = _rows(records, name)
    return values


def _build_crossfit(*, records: dict[str, list[dict[str, Any]]], angles: np.ndarray,
                    truth: np.ndarray, split: list[tuple[np.ndarray, np.ndarray]],
                    windows_path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    values = {name: _predictor_rows(records, name) for name in (Q1, Q2, "L1_local_rbf_k24_s1e-08", "L2_local_matern_k32")}
    fold_train: list[np.ndarray | None] = [None] * len(angles)
    for train, test in split:
        for index in test:
            fold_train[int(index)] = train
    raw = _component_raw(angles, records, fold_train=fold_train,
                         train_angles=None, train_masks=None)
    risk_by_fold = np.full(len(angles), np.nan, dtype=np.float64)
    components_by_fold: dict[str, np.ndarray] = {}
    fold_rows: dict[str, list[dict[str, Any]]] = {name: [] for name in PREDICTORS}
    oof_records: dict[str, list[dict[str, Any]]] = {name: [] for name in PREDICTORS}
    final_results: dict[str, Any] = {}
    for predictor in PREDICTORS:
        prediction = values[predictor]["prediction"]
        predictor_std = values[predictor]["std"]
        accepted = np.zeros(len(angles), dtype=bool)
        radii = np.full((len(angles), 3), np.nan, dtype=np.float64)
        threshold_qualified = True
        for fold, (_, test) in enumerate(split):
            source = np.asarray(sorted(set(range(len(angles))) - set(test.tolist())), dtype=np.int64)
            bounds = _fit_bounds(raw, source)
            risk, components = _risk_from_raw(raw, bounds, S1)
            risk_by_fold[test] = risk[test]
            for key, array in components.items():
                if key not in components_by_fold:
                    shape = (len(angles),) if np.ndim(array) == 1 else (len(angles), array.shape[1])
                    components_by_fold[key] = np.full(shape, np.nan, dtype=np.float64)
                components_by_fold[key][test] = array[test]
            threshold = _source_threshold(source, risk, truth, prediction, windows_path)
            selected = threshold.get("selected")
            if selected is None:
                threshold_qualified = False
                # No fallback is permitted.  Keep the risk for diagnostics but
                # mark this held-out fold rejected and leave interval undefined.
                test_accept = np.zeros(len(test), dtype=bool)
                source_accepted = np.empty(0, dtype=np.int64)
                radius = np.full(3, np.nan, dtype=np.float64)
            else:
                test_accept = risk[test] <= float(selected["threshold"]) + 1.0e-15
                source_accepted = np.asarray(selected["accepted_indices"], dtype=np.int64)
                radius = np.asarray([
                    _finite_conformal_quantile(np.abs(prediction[source_accepted, i] - truth[source_accepted, i]))
                    for i in range(3)
                ], dtype=np.float64)
                if not np.isfinite(radius).all() or np.any(radius <= 0.0):
                    threshold_qualified = False
                radii[test] = radius[None, :]
            accepted[test] = test_accept
            fold_rows[predictor].append({
                "fold": fold, "test_indices": test.tolist(), "source_indices": source.tolist(),
                "source_outer_folds": [k for k in range(len(split)) if k != fold],
                "normalization_bounds": bounds, "threshold": threshold,
                "source_accepted_indices": source_accepted.astype(int).tolist(),
                "source_accepted_count": int(len(source_accepted)),
                "conformal_radii": radius.tolist(),
                "held_out_response_used_for_threshold": False,
                "held_out_response_used_for_interval": False,
                "no_fallback": selected is not None,
            })
        accepted_idx = np.flatnonzero(accepted)
        accuracy_gate, metrics = _point_accuracy_gate(truth, prediction, accepted_idx)
        windows, _ = _window_report(truth, prediction, accepted, windows_path)
        supported_gate = _supported_gate_allow_empty(windows)
        composition_gate = bool(len(accepted_idx) > 0 and _composition_exact(prediction[accepted_idx]))
        conformal = _conformal_report(truth, prediction, predictor_std, accepted, radii)
        threshold_gate = bool(threshold_qualified and all(
            row["no_fallback"] and row["held_out_response_used_for_threshold"] is False and
            row["held_out_response_used_for_interval"] is False for row in fold_rows[predictor]
        ))
        result = {
            "predictor": predictor, "risk_rule": S1,
            "accepted_indices": accepted_idx.astype(int).tolist(),
            "rejected_indices": np.flatnonzero(~accepted).astype(int).tolist(),
            "accepted_count": int(len(accepted_idx)),
            "accepted_fraction": float(len(accepted_idx) / len(angles)),
            "metrics_accepted": metrics, "accepted_accuracy_gate": accuracy_gate,
            "supported_window_metrics": windows, "accepted_supported_window_gate": supported_gate,
            "accepted_composition_gate": composition_gate,
            "threshold_gate": threshold_gate, "conditional_conformal": conformal,
            "folds": fold_rows[predictor],
            "response_used_for_acceptance": False,
        }
        final_results[predictor] = result
        for index in range(len(angles)):
            fold = int(values[predictor]["fold"][index])
            fold_item = fold_rows[predictor][fold]
            threshold_data = fold_item["threshold"]
            selected = threshold_data.get("selected") if threshold_data else None
            row = {
                "sample_index": index, "angle": angles[index].round(12).tolist(),
                "identity": "old96" if index < 96 else "new16", "fold": fold,
                "predictor": predictor, "risk_rule": S1,
                "truth": truth[index].tolist(), "prediction": prediction[index].tolist(),
                "std": predictor_std[index].tolist(),
                "error": (prediction[index] - truth[index]).tolist(),
                "absolute_error": np.abs(prediction[index] - truth[index]).tolist(),
                "risk_score": float(risk_by_fold[index]),
                "risk_components": {key: (value[index].tolist() if np.ndim(value) else float(value[index]))
                                    for key, value in components_by_fold.items()},
                "threshold": None if selected is None else float(selected["threshold"]),
                "threshold_quantile": None if selected is None else float(selected["quantile"]),
                "threshold_source_folds": fold_item["source_outer_folds"],
                "threshold_source_indices_hash": canonical_hash(fold_item["source_indices"]),
                "threshold_source_gate": bool(fold_item["no_fallback"]),
                "accepted": bool(accepted[index]),
                "reason": "accepted_training_risk" if accepted[index] else "requires_fem_threshold_or_risk",
                "conformal_half_width": radii[index].tolist(),
                "interval": {
                    "lower_unclipped": (prediction[index] - radii[index]).tolist(),
                    "upper_unclipped": (prediction[index] + radii[index]).tolist(),
                    "lower_clipped": np.clip(prediction[index] - radii[index], 0.0, 1.0).tolist(),
                    "upper_clipped": np.clip(prediction[index] + radii[index], 0.0, 1.0).tolist(),
                },
                "interval_response_used_for_calibration": False,
                "cutoff_margin": float(raw["cutoff_margin"][index]),
                "mask_signature": str(raw["mask_signature"][index]),
                "topology_supported_in_outer_train": bool(raw["topology_supported"][index]),
            }
            oof_records[predictor].append(row)
    return {"results": final_results, "fold_rows": fold_rows,
            "fold_seed": FOLD_SEED, "risk_rule": S1}, oof_records


def _final_quantile_and_screen(*, crossfit: dict[str, Any], records: dict[str, list[dict[str, Any]]],
                               angles: np.ndarray, aggregates: np.ndarray, masks: np.ndarray,
                               split: list[tuple[np.ndarray, np.ndarray]], windows_path: Path,
                               pool_path: Path, blind_path: Path) -> dict[str, Any]:
    fold_train: list[np.ndarray | None] = [None] * len(angles)
    for train, test in split:
        for index in test:
            fold_train[int(index)] = train
    raw = _component_raw(angles, records, fold_train=fold_train,
                         train_angles=None, train_masks=None)
    final_bounds = _fit_bounds(raw, np.arange(len(angles), dtype=np.int64))
    final_bounds_payload = {S1: final_bounds,
                            # _screen_design is the shared response-blind
                            # helper and emits its historical S2 diagnostic as
                            # well; M4I never uses that candidate in a Gate.
                            S2: _fit_bounds(raw, np.arange(len(angles), dtype=np.int64))}
    final_thresholds: dict[str, float | None] = {}
    final_quantiles: dict[str, float | None] = {}
    unified_risk, _ = _risk_from_raw(raw, final_bounds, S1)
    for predictor in PREDICTORS:
        fold_q = [float(row["threshold"]["selected"]["quantile"])
                  for row in crossfit["fold_rows"][predictor]
                  if row["threshold"].get("selected") is not None]
        if len(fold_q) != len(split):
            final_quantiles[predictor] = None; final_thresholds[predictor] = None
        else:
            final_q = float(np.median(fold_q))
            final_quantiles[predictor] = final_q
            final_thresholds[predictor] = float(np.quantile(unified_risk, final_q, method="linear"))
    pool_payload = json.loads(pool_path.read_text())
    pool_angles = np.asarray([[float(row["grazing_deg"]), float(row["azimuth_deg"])]
                              for row in pool_payload["points"]], dtype=np.float64)
    blind_payload = json.loads(blind_path.read_text())
    blind_angles = np.asarray([[float(row["grazing_deg"]), float(row["azimuth_deg"])]
                               for row in blind_payload["points"]], dtype=np.float64)
    if any(value is None for value in final_thresholds.values()):
        return {"final_bounds": final_bounds_payload, "final_quantiles": final_quantiles,
                "final_thresholds": final_thresholds, "unified_oof_risk": unified_risk.tolist(),
                "pool": None, "blind": None, "pool_payload": pool_payload,
                "blind_payload": blind_payload}
    screen_thresholds = {f"{predictor}::{S1}": float(final_thresholds[predictor])
                         for predictor in PREDICTORS}
    # m4h._screen_design requires thresholds for the complete finite internal
    # set; add the two diagnostic entries but retain only Q1/Q2 below.
    for name in (P1, P2, P3):
        screen_thresholds.setdefault(f"{name}::{S1}", float(final_thresholds[Q1]))
        screen_thresholds.setdefault(f"{name}::{S2}", 1.0)
    pool = _screen_design(pool_angles, angles, aggregates, masks, final_bounds_payload,
                          screen_thresholds, "candidate_pool_4096")
    blind = _screen_design(blind_angles, angles, aggregates, masks, final_bounds_payload,
                           screen_thresholds, "blind_design_24")
    return {"final_bounds": final_bounds_payload, "final_quantiles": final_quantiles,
            "final_thresholds": final_thresholds, "unified_oof_risk": unified_risk.tolist(),
            "pool": pool, "blind": blind, "pool_payload": pool_payload,
            "blind_payload": blind_payload}


def _selection_key(result: dict[str, Any]) -> tuple[Any, ...]:
    metrics = result["metrics_accepted"]
    max_abs = max(float(item["max_abs"]) for item in metrics.values())
    p95 = max(float(item["p95_abs"]) for item in metrics.values())
    return max_abs, p95, -float(result["accepted_fraction"]), str(result["predictor"])


def run_m4i(*, dataset_dir: Path, output_dir: Path, folds_path: Path,
            oof_path: Path, windows_path: Path, candidate_pool_path: Path,
            blind_design_path: Path, implementation_sha: str) -> dict[str, Any]:
    manifest = verify_immutable_package(dataset_dir, expected_dataset_id=DATASET_ID)
    data = load_training_dataset(dataset_dir)
    angles = np.asarray(data["angles.npy"], dtype=np.float64)
    aggregates = np.asarray(data["aggregates.npy"], dtype=np.float64)[:, :3]
    masks = np.asarray(data["power_carrying_mask.npy"], dtype=bool)
    if manifest.get("forward_solver_sha") != FORWARD_SHA or manifest.get("validation_target_accessed") is not False:
        raise ValueError("M4I immutable train112 identity failed")
    oof_payload = json.loads(oof_path.read_text())
    if oof_payload.get("dataset_id") != DATASET_ID or oof_payload.get("validation_target_accessed") is not False:
        raise ValueError("M4I OOF identity/validation guard failed")
    records = oof_payload["records"]
    split, fold_meta = _fold_data(folds_path, angles, masks)
    truth = np.asarray([row["truth"] for row in records[Q1]], dtype=np.float64)
    crossfit, oof_records = _build_crossfit(records=records, angles=angles, truth=truth,
                                             split=split, windows_path=windows_path)
    screen = _final_quantile_and_screen(crossfit=crossfit, records=records, angles=angles,
                                        aggregates=aggregates, masks=masks, split=split,
                                        windows_path=windows_path, pool_path=candidate_pool_path,
                                        blind_path=blind_design_path)
    comparisons: dict[str, Any] = {}
    for predictor in PREDICTORS:
        result = crossfit["results"][predictor]
        pool_item = None if screen["pool"] is None else screen["pool"]["predictor_screening"][f"{predictor}::{S1}"]
        blind_item = None if screen["blind"] is None else screen["blind"]["predictor_screening"][f"{predictor}::{S1}"]
        if pool_item is None or blind_item is None:
            pool_fraction = 0.0; blind_count = 0
        else:
            pool_fraction = float(pool_item["accepted_fraction"])
            blind_count = int(blind_item["accepted_count"])
        gates = {
            "accepted_oof_fraction": result["accepted_fraction"] >= MIN_ACCEPTED_FRACTION,
            "candidate_pool_accepted_fraction": pool_fraction >= MIN_ACCEPTED_FRACTION,
            "blind_design_accepted_count": blind_count >= MIN_BLIND_ACCEPTED,
            "accepted_point_accuracy": result["accepted_accuracy_gate"],
            "accepted_supported_window": result["accepted_supported_window_gate"],
            "accepted_composition": result["accepted_composition_gate"],
            "predictor_specific_thresholds_no_fallback": result["threshold_gate"],
            "conditional_conformal_coverage": result["conditional_conformal"]["coverage_gate"],
            "conditional_conformal_sharpness": result["conditional_conformal"]["sharpness_gate"],
        }
        comparisons[predictor] = {**result,
                                  "final_quantile": screen["final_quantiles"][predictor],
                                  "final_production_threshold": screen["final_thresholds"][predictor],
                                  "unified_oof_acceptance_fraction": None if screen["final_thresholds"][predictor] is None else
                                  float(np.mean(np.asarray(screen["unified_oof_risk"]) <= screen["final_thresholds"][predictor] + 1.0e-15)),
                                  "candidate_pool_accepted_count": 0 if pool_item is None else pool_item["accepted_count"],
                                  "candidate_pool_accepted_fraction": pool_fraction,
                                  "blind_design_accepted_count": blind_count,
                                  "blind_design_accepted_indices": [] if blind_item is None else blind_item["accepted_indices"],
                                  "gates": gates, "all_training_gates": bool(all(gates.values()))}
    qualified = [value for value in comparisons.values() if value["all_training_gates"]]
    selected = min(qualified, key=_selection_key) if qualified else None
    pool_payload = screen["pool"]; blind_payload = screen["blind"]
    lock_created = selected is not None
    lock = None
    if lock_created:
        selected_name = selected["predictor"]
        blind_item = blind_payload["predictor_screening"][f"{selected_name}::{S1}"]
        train_hashes = json.loads((dataset_dir / "file_hashes.json").read_text())
        lock = {
            "schema_version": "task004.angle-aggregate-selective-model-selection-lock.v3",
            "dataset_id": DATASET_ID, "forward_solver_sha": FORWARD_SHA,
            "surrogate_training_code_sha": implementation_sha,
            "training_tuple_sha256": manifest["training_tuple_sha256"],
            "dataset_file_hashes": train_hashes,
            "fold_seed": FOLD_SEED, "fold_identity": fold_meta["payload"]["fold_identity"],
            "point_predictor": selected_name, "risk_rule": S1,
            "risk_formula": "pre-frozen M4E2 S1; predictor-specific source thresholds",
            "per_fold_thresholds": selected["folds"],
            "final_quantile": selected["final_quantile"],
            "final_production_threshold": selected["final_production_threshold"],
            "final_normalization": screen["final_bounds"][S1],
            "conditional_conformal": selected["conditional_conformal"],
            "training_metrics": selected,
            "candidate_pool": pool_payload["predictor_screening"][f"{selected_name}::{S1}"],
            "blind_design": blind_item,
            "blind_accepted_indices": blind_item["accepted_indices"],
            "blind_rejected_indices": blind_item["rejected_indices"],
            "blind_preacceptance_frozen": True,
            "order_resolved_qualified": False,
            "validation_target_accessed": False,
            "blind_fem_authorized": True,
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    threshold_payload = {
        "schema_version": "task004.selective-threshold-correction.v1",
        "dataset_id": DATASET_ID, "forward_solver_sha": FORWARD_SHA,
        "surrogate_training_code_sha": implementation_sha,
        "predictors": list(PREDICTORS), "risk_rule": S1,
        "quantile_grid": list(QUANTILES), "minimum_accepted_fraction": MIN_ACCEPTED_FRACTION,
        "selection_contract": "highest accepted fraction among source-Gate-passing quantiles; then lower point-error score; then lower threshold",
        "predictor_results": {name: {"folds": crossfit["fold_rows"][name],
                                     "final_quantile": comparisons[name]["final_quantile"],
                                     "final_threshold": comparisons[name]["final_production_threshold"],
                                     "unified_oof_acceptance_fraction": comparisons[name]["unified_oof_acceptance_fraction"]}
                             for name in PREDICTORS},
        "validation_response_accessed": False,
    }
    conformal_payload = {
        "schema_version": "task004.selective-conditional-conformal.v1",
        "dataset_id": DATASET_ID, "forward_solver_sha": FORWARD_SHA,
        "surrogate_training_code_sha": implementation_sha,
        "method": "accepted-source-OOF absolute residual finite-sample 95th conformal quantile",
        "formula": "radius_t=quantile_higher(abs(prediction_source_accepted-truth_source_accepted), ceil((n+1)*0.95)/n)",
        "predictors": {name: comparisons[name]["conditional_conformal"] for name in PREDICTORS},
        "coverage_lower_bound": CONFORMAL_COVERAGE,
        "p95_half_width_upper_bound": MAX_P95_HALF_WIDTH,
        "max_half_width_upper_bound": MAX_HALF_WIDTH,
        "old_coverage_upper_bound": "warning_only",
        "validation_response_accessed": False,
    }
    comparison_payload = {
        "schema_version": "task004.selective-model-comparison.v2",
        "dataset_id": DATASET_ID, "forward_solver_sha": FORWARD_SHA,
        "surrogate_training_code_sha": implementation_sha,
        "candidate_set": list(PREDICTORS), "risk_rule_set": [S1],
        "results": comparisons, "selected_candidate": None if selected is None else selected["predictor"],
        "selection_order": ["max_absolute_error", "p95_absolute_error", "accepted_fraction", "candidate_name"],
        "model_lock_created": lock_created, "validation_response_accessed": False,
    }
    acceptance_payload = {
        "schema_version": "task004.selective-acceptance-domain.v2",
        "dataset_id": DATASET_ID, "forward_solver_sha": FORWARD_SHA,
        "surrogate_training_code_sha": implementation_sha,
        "candidate_pool": None if screen["pool"] is None else {
            key: screen["pool"]["predictor_screening"][key]
            for key in (f"{Q1}::{S1}", f"{Q2}::{S1}")
        },
        "blind_design": None if screen["blind"] is None else {
            key: screen["blind"]["predictor_screening"][key]
            for key in (f"{Q1}::{S1}", f"{Q2}::{S1}")
        },
        "candidate_pool_design_id": screen["pool_payload"].get("design_id"),
        "candidate_pool_tuple_sha256": screen["pool_payload"].get("point_tuple_sha256"),
        "blind_design_id": screen["blind_payload"].get("design_id"),
        "blind_tuple_sha256": screen["blind_payload"].get("point_tuple_sha256"),
        "response_blind": True, "validation_response_accessed": False,
    }
    (output_dir / "SELECTIVE_THRESHOLD_CORRECTION.json").write_text(json.dumps(threshold_payload, indent=2, sort_keys=True) + "\n")
    (output_dir / "SELECTIVE_CONDITIONAL_CONFORMAL.json").write_text(json.dumps(conformal_payload, indent=2, sort_keys=True) + "\n")
    (output_dir / "SELECTIVE_MODEL_COMPARISON_V2.json").write_text(json.dumps(comparison_payload, indent=2, sort_keys=True) + "\n")
    (output_dir / "SELECTIVE_ACCEPTANCE_DOMAIN_V2.json").write_text(json.dumps(acceptance_payload, indent=2, sort_keys=True) + "\n")
    (output_dir / "SELECTIVE_OOF_V2.json").write_text(json.dumps({
        "schema_version": "task004.selective-oof.v2", "dataset_id": DATASET_ID,
        "records": oof_records, "validation_response_accessed": False}, indent=2, sort_keys=True) + "\n")
    lock_path = output_dir / "ANGLE_AGGREGATE_SELECTIVE_MODEL_SELECTION_LOCK.json"
    if lock_created:
        lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    elif lock_path.exists():
        lock_path.unlink()
    return {"threshold": threshold_payload, "conformal": conformal_payload,
            "comparison": comparison_payload, "crossfit": crossfit,
            "screen": screen, "lock": lock, "oof_records": oof_records}
