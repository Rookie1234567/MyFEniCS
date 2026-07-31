"""M3T fixed-reference audit and Round-1 prospective acquisition audit.

This module reads only the 96 training view, the 104 training view, and input
metadata for the eight already-measured points.  It never opens validation
targets or launches a FEM process.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .dataset import CASE119_ROOT, load_training_dataset
from .features import transform_feature_candidate
from .folds import FOLD_SEED, fold_identity, folds
from .models import ExactARDGP, TrendResidualGP
from .physics import reconstruct_aggregates
from .targets import aggregate_log_ratios
from .cv import _composition_std, _metrics, _regions


ROUND1_DATASET = Path("benchmarks/artifacts/cases/121_task003_active_learning_round1_retry_cachefix/compact_dataset")
OUT = Path("surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/outcomes")
PLAN = OUT / "ACTIVE_LEARNING_ROUND1_PLAN.json"
CASE122 = Path("benchmarks/cases/122_task003_round1_fixed_reference_and_optional_round2")


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _fit_predict(family: str, x_train: np.ndarray, y_train: np.ndarray,
                 x_test: np.ndarray, *, seed: int = 41) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    means = []; stds = []; metadata = []
    for latent_index in range(2):
        if family == "G1_constant_gp":
            model = ExactARDGP(jitter=1.0e-10, optimizer_restarts=8,
                               random_state=seed + latent_index)
        elif family == "G2_degree2_trend_residual_gp":
            model = TrendResidualGP(jitter=1.0e-10, optimizer_restarts=8,
                                    random_state=seed + latent_index)
        else:
            raise ValueError(f"unknown M3T family {family}")
        model.fit(x_train, y_train[:, latent_index])
        mean, std = model.predict(x_test, return_std=True)
        means.append(mean); stds.append(std); metadata.append(model.metadata())
    return np.column_stack(means), np.column_stack(stds), {"family": family, "latents": metadata}


def _aggregate_metrics(truth: np.ndarray, latent_prediction: np.ndarray) -> dict[str, Any]:
    prediction = reconstruct_aggregates(latent_prediction)[:, :3]
    return {name: _metrics(truth[:, i], prediction[:, i])
            for i, name in enumerate(("R_total", "T_total", "A_balance"))}


def _paired_model(old: Any, enriched: Any, split: list[tuple[np.ndarray, np.ndarray]],
                  family: str) -> dict[str, Any]:
    x_old = transform_feature_candidate(old.inputs, "B")
    x_new = transform_feature_candidate(enriched.inputs, "B")
    y_old = aggregate_log_ratios(old.aggregates)
    y_new = aggregate_log_ratios(enriched.aggregates)
    pred_old = np.full((96, 2), np.nan); std_old = np.full((96, 2), np.nan)
    pred_new = np.full((96, 2), np.nan); std_new = np.full((96, 2), np.nan)
    fold_rows = []
    for fold_index, (train, test) in enumerate(split):
        old_mean, old_std, old_fit = _fit_predict(family, x_old[train], y_old[train], x_old[test])
        extra = np.arange(96, 104, dtype=np.int64)
        new_train = np.concatenate((train, extra))
        new_mean, new_std, new_fit = _fit_predict(family, x_new[new_train], y_new[new_train], x_new[test])
        pred_old[test] = old_mean; std_old[test] = old_std
        pred_new[test] = new_mean; std_new[test] = new_std
        fold_rows.append({"fold": fold_index, "test_indices": test.tolist(),
                          "baseline96_fit": old_fit, "enriched104_fit": new_fit})
    truth = old.aggregates[:, :3]
    old_comp = reconstruct_aggregates(pred_old)[:, :3]
    new_comp = reconstruct_aggregates(pred_new)[:, :3]
    metrics_old = _aggregate_metrics(truth, pred_old)
    metrics_new = _aggregate_metrics(truth, pred_new)
    regions = _regions(old.inputs)
    paired = []
    for row in range(96):
        for index, name in enumerate(("R_total", "T_total", "A_balance")):
            err_old = float(old_comp[row, index] - truth[row, index])
            err_new = float(new_comp[row, index] - truth[row, index])
            paired.append({"sample_index": row, "target": name, "fold": next(i for i, (_, te) in enumerate(split) if row in te),
                           "truth": float(truth[row, index]), "baseline96_prediction": float(old_comp[row, index]),
                           "enriched104_prediction": float(new_comp[row, index]),
                           "baseline96_abs_error": abs(err_old), "enriched104_abs_error": abs(err_new),
                           "paired_abs_error_delta": abs(err_new) - abs(err_old),
                           "baseline96_std": float(std_old[row, min(index, 1)]),
                           "enriched104_std": float(std_new[row, min(index, 1)]),
                           "regions": regions[row]})
    region_breakdown = {}
    for region in sorted({name for row in regions for name in row}):
        selected = np.asarray([region in row for row in regions])
        region_breakdown[region] = {
            "count": int(selected.sum()),
            "baseline96": {name: _metrics(truth[selected, i], old_comp[selected, i]) for i, name in enumerate(("R_total", "T_total", "A_balance"))},
            "enriched104": {name: _metrics(truth[selected, i], new_comp[selected, i]) for i, name in enumerate(("R_total", "T_total", "A_balance"))},
        }
    return {"family": family, "baseline96_metrics": metrics_old,
            "enriched104_metrics": metrics_new, "folds": fold_rows,
            "paired_records": paired, "region_breakdown": region_breakdown}


def _improvement(old_metric: dict[str, Any], new_metric: dict[str, Any]) -> dict[str, float]:
    return {key: float((old_metric[key] - new_metric[key]) / old_metric[key])
            for key in ("nrmse", "p95_abs", "p95_relative_truth_ge_1e-2", "max_abs")
            if old_metric.get(key) not in (None, 0) and new_metric.get(key) is not None}


def _prospective_audit(old: Any, enriched: Any) -> dict[str, Any]:
    plan = json.loads(PLAN.read_text())
    points = enriched.inputs[96:104]
    truth = enriched.aggregates[96:104, :3]
    x_old = transform_feature_candidate(old.inputs, "B")
    y_old = aggregate_log_ratios(old.aggregates)
    x_points = transform_feature_candidate(points, "B")
    rows = []
    for family in ("G1_constant_gp", "G2_degree2_trend_residual_gp"):
        latent, std, fit = _fit_predict(family, x_old, y_old, x_points)
        reconstructed = reconstruct_aggregates(latent)
        prediction = reconstructed[:, :3]
        aggregate_std = _composition_std(std, reconstructed)[:, :3]
        for index in range(8):
            error = prediction[index] - truth[index]
            rows.append({"model_family": family, "point_index": index,
                         "point": points[index].tolist(), "truth": truth[index].tolist(),
                         "prediction": prediction[index].tolist(),
                         "absolute_error": np.abs(error).tolist(),
                         "relative_error_truth_ge_1e-2": (np.abs(error) / np.maximum(truth[index], 1.0e-2)).tolist(),
                         "standardized_error": (np.abs(error) / np.maximum(aggregate_std[index], 1.0e-12)).tolist(),
                         "predicted_std_latent": std[index].tolist(),
                         "acquisition": plan["points"][index], "fit_metadata": fit})
    loo_rows = []
    x_all = transform_feature_candidate(enriched.inputs, "B")
    y_all = aggregate_log_ratios(enriched.aggregates)
    for family in ("G1_constant_gp", "G2_degree2_trend_residual_gp"):
        for left in range(8):
            keep = np.asarray([i for i in range(8) if i != left], dtype=np.int64)
            train = np.concatenate((np.arange(96), 96 + keep))
            latent, std, _fit = _fit_predict(family, x_all[train], y_all[train], x_all[96 + left:97 + left])
            reconstructed = reconstruct_aggregates(latent)
            prediction = reconstructed[0, :3]
            aggregate_std = _composition_std(std, reconstructed)[0, :3]
            error = prediction - truth[left]
            loo_rows.append({"model_family": family, "left_out_point_index": left,
                             "absolute_error": np.abs(error).tolist(),
                             "standardized_error": (np.abs(error) / np.maximum(aggregate_std, 1.0e-12)).tolist()})
    return {"schema_version": "task003.round1-prospective-audit.v1",
            "validation_target_accessed": False, "rows": rows,
            "leave_one_new_point_out": loo_rows}


def run() -> dict[str, Any]:
    old = load_training_dataset(CASE119_ROOT)
    enriched = load_training_dataset(ROUND1_DATASET)
    if old.n_samples != 96 or enriched.n_samples != 104:
        raise RuntimeError("M3T requires 96 and 104 training views")
    if not np.array_equal(old.inputs, enriched.inputs[:96]):
        raise RuntimeError("Round1 dataset changed the original 96 training rows")
    x_old = transform_feature_candidate(old.inputs, "B")
    split = folds(x_old, n_splits=5, seed=FOLD_SEED)
    reference = fold_identity(x_old, split, seed=FOLD_SEED)
    reference.update({"dataset_id": old.dataset_id, "training_count": 96,
                      "feature_candidate": "B", "validation_target_accessed": False,
                      "point_tuple_sha256": _hash(old.inputs.tolist())})
    (OUT / "BASE96_REFERENCE_FOLDS.json").write_text(json.dumps(reference, indent=2) + "\n")
    comparisons = [_paired_model(old, enriched, split, family)
                   for family in ("G1_constant_gp", "G2_degree2_trend_residual_gp")]
    for comparison in comparisons:
        comparison["improvement"] = {
            target: _improvement(comparison["baseline96_metrics"][target], comparison["enriched104_metrics"][target])
            for target in ("R_total", "T_total", "A_balance")
        }
    prospective = _prospective_audit(old, enriched)
    primary = next(item for item in comparisons if item["family"] == "G2_degree2_trend_residual_gp")
    imp = primary["improvement"]
    paired_p95_improved = sum(imp[name]["p95_abs"] > 0 for name in ("R_total", "T_total", "A_balance")) >= 2
    gate = {
        "reference_folds_frozen": True,
        "R_total_nrmse_improvement_ge_10pct": imp["R_total"]["nrmse"] >= 0.10,
        "A_balance_nrmse_improvement_ge_10pct": imp["A_balance"]["nrmse"] >= 0.10,
        "T_total_nrmse_not_worse_than_10pct": imp["T_total"]["nrmse"] >= -0.10,
        "at_least_two_paired_p95_abs_improved": paired_p95_improved,
        "prospective_audit_present": len(prospective["rows"]) == 16,
        "validation_target_accessed": False,
    }
    gate_pass = bool(all(value for key, value in gate.items() if key != "validation_target_accessed")
                     and gate["validation_target_accessed"] is False)
    result = {"schema_version": "task003.m3t-fixed-reference-audit.v1",
              "validation_target_accessed": False, "reference": reference,
              "comparisons": comparisons, "prospective_audit": prospective,
              "round2_gate": gate, "round2_authorized": gate_pass}
    (OUT / "ROUND1_FIXED_REFERENCE_AUDIT.json").write_text(json.dumps({
        "schema_version": "task003.round1-fixed-reference-audit.v1",
        "validation_target_accessed": False,
        "reference_fold_sha256": reference["fold_sha256"],
        "comparisons": [{key: item[key] for key in
                         ("family", "baseline96_metrics", "enriched104_metrics",
                          "improvement", "region_breakdown", "paired_records")}
                        for item in comparisons],
        "prospective_audit": prospective,
        "round2_gate": gate, "round2_authorized": gate_pass,
    }, indent=2) + "\n")
    (OUT / "ROUND1_COMPLETION_STATUS.json").write_text(json.dumps({
        "schema_version": "task003.round1-completion-status.v2", "training_count": 104,
        "frozen_validation_count": 16, "active_learning_round1_points": 8,
        "active_learning_total_points_used": 8,
        "selected_104_candidate": "G2_degree2_trend_residual_gp:features=B:jitter=1e-10",
        "validation_target_accessed": False, "round2_status": "authorized_pending_plan" if gate_pass else "forbidden_gate_failed",
        "round2_gate": gate, "round2_authorized": gate_pass,
    }, indent=2) + "\n")
    (OUT / "ROUND1_DATASET_VERIFICATION.json").write_text(json.dumps({
        "schema_version": "task003.round1-dataset-verification.v1", "dataset_id": enriched.dataset_id,
        "training_count": 104, "frozen_validation_count": 16,
        "original96_unchanged": bool(np.array_equal(old.inputs, enriched.inputs[:96])),
        "round1_count": 8, "validation_target_accessed": False,
    }, indent=2) + "\n")
    return result


if __name__ == "__main__":
    output = run()
    print(json.dumps({"round2_authorized": output["round2_authorized"], "gate": output["round2_gate"]}, indent=2))
