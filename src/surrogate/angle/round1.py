"""Task004 M4F round-1 train112 assembly and paired learning curve.

This module only consumes the immutable train96 package and the sixteen
measured-pass round-1 records.  It never opens a validation response.  The
paired curve deliberately keeps the five train96 test rows fixed: the 112-row
fit adds all sixteen new points to each fold's training side.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from ..folds import FOLD_SEED, fold_identity, folds
from .dataset import load_training_dataset, verify_immutable_package
from .m4e import _make_candidate, _metrics
from .models import angle_features


PAIRED_SPECS = (
    {"candidate": "L1_local_rbf_k24_s1e-08", "family": "local_rbf",
     "neighbors": 24, "smoothing": 1.0e-8, "feature": "F1"},
    {"candidate": "L2_local_matern_k24", "family": "local_matern",
     "neighbors": 24, "jitter": 1.0e-8, "feature": "F1"},
    {"candidate": "L2_local_matern_k32", "family": "local_matern",
     "neighbors": 32, "jitter": 1.0e-8, "feature": "F1"},
)


def _fit_side(spec: dict[str, Any], angles: np.ndarray, truth: np.ndarray,
              train: np.ndarray, test_angles: np.ndarray) -> np.ndarray:
    model = _make_candidate(spec).fit(angles[train], truth[train])
    return np.asarray(model.predict(test_angles)[0], dtype=np.float64)


def run_paired_learning_curve(*, train96_dir: Path, train112_dir: Path,
                              output_dir: Path, implementation_sha: str) -> dict[str, Any]:
    manifest96 = verify_immutable_package(train96_dir)
    manifest112 = verify_immutable_package(train112_dir)
    if manifest96.get("training_count") != 96 or manifest112.get("training_count") != 112:
        raise ValueError("paired Task004 curve requires immutable 96 and 112 packages")
    data96 = load_training_dataset(train96_dir)
    data112 = load_training_dataset(train112_dir)
    angles96 = np.asarray(data96["angles.npy"], dtype=np.float64)
    angles112 = np.asarray(data112["angles.npy"], dtype=np.float64)
    truth96 = np.asarray(data96["aggregates.npy"], dtype=np.float64)[:, :3]
    truth112 = np.asarray(data112["aggregates.npy"], dtype=np.float64)[:, :3]
    if not np.array_equal(angles112[:96], angles96) or not np.allclose(truth112[:96], truth96):
        raise ValueError("train112 does not preserve train96 prefix exactly")
    split = folds(angle_features(angles96, "F1"), n_splits=5, seed=FOLD_SEED)
    split_id = fold_identity(angle_features(angles96, "F1"), split, seed=FOLD_SEED)
    new_indices = np.arange(96, 112, dtype=np.int64)
    results: dict[str, Any] = {}
    for spec in PAIRED_SPECS:
        pred96 = np.full((96, 3), np.nan)
        pred112 = np.full((96, 3), np.nan)
        rows = []
        fold_rows = []
        for fold, (train, test) in enumerate(split):
            train_augmented = np.concatenate((train, new_indices))
            p96 = _fit_side(spec, angles96, truth96, train, angles96[test])
            p112 = _fit_side(spec, angles112, truth112, train_augmented, angles96[test])
            pred96[test] = p96
            pred112[test] = p112
            fold_rows.append({"fold": fold, "test_indices": test.tolist(),
                              "train96_indices": train.tolist(),
                              "train112_indices": train_augmented.tolist()})
            for local, index in enumerate(test):
                rows.append({
                    "sample_index": int(index), "fold": int(fold),
                    "angle": angles96[index].round(12).tolist(),
                    "truth": truth96[index].tolist(),
                    "prediction_train96": p96[local].tolist(),
                    "prediction_train112": p112[local].tolist(),
                    "error_train96": (p96[local] - truth96[index]).tolist(),
                    "error_train112": (p112[local] - truth96[index]).tolist(),
                    "absolute_error_train96": np.abs(p96[local] - truth96[index]).tolist(),
                    "absolute_error_train112": np.abs(p112[local] - truth96[index]).tolist(),
                    "absolute_error_delta_112_minus_96": (
                        np.abs(p112[local] - truth96[index]) -
                        np.abs(p96[local] - truth96[index])
                    ).tolist(),
                })
        metrics96 = {target: _metrics(truth96[:, i], pred96[:, i])
                     for i, target in enumerate(("R_total", "T_total", "A_balance"))}
        metrics112 = {target: _metrics(truth96[:, i], pred112[:, i])
                      for i, target in enumerate(("R_total", "T_total", "A_balance"))}
        results[spec["candidate"]] = {
            **spec, "metrics_train96": metrics96, "metrics_train112": metrics112,
            "max_error_reduction": float(np.max(np.abs(pred96 - truth96)) -
                                          np.max(np.abs(pred112 - truth96))),
            "mean_absolute_error_reduction": float(np.mean(np.abs(pred96 - truth96)) -
                                                    np.mean(np.abs(pred112 - truth96))),
            "folds": fold_rows, "points": sorted(rows, key=lambda row: row["sample_index"]),
        }
    report = {
        "schema_version": "task004.paired-learning-curve.112.v1",
        "dataset96_id": manifest96["dataset_id"],
        "dataset112_id": manifest112["dataset_id"],
        "forward_solver_sha": manifest112["forward_solver_sha"],
        "surrogate_training_code_sha": implementation_sha,
        "train96_tuple_sha256": manifest96["training_tuple_sha256"],
        "train112_tuple_sha256": manifest112["training_tuple_sha256"],
        "fold_identity": split_id,
        "test_rows_fixed_to_train96": True,
        "train112_additional_indices": new_indices.tolist(),
        "validation_target_accessed": False,
        "selected_final_candidate": "L1_local_rbf_k24_s1e-08",
        "candidates": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "paired_learning_curve_96_to_112.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    lines = ["# Paired train96 → train112 learning curve", "",
             "The test rows are the same five-fold train96 test rows; each train112 fit adds all 16 new FEM points.", "",
             "| candidate | train96 max abs | train112 max abs | max-error reduction | mean-abs reduction |", "|---|---:|---:|---:|---:|"]
    for name, item in results.items():
        max96 = max(x["max_abs"] for x in item["metrics_train96"].values())
        max112 = max(x["max_abs"] for x in item["metrics_train112"].values())
        lines.append(f"| {name} | {max96:.8g} | {max112:.8g} | {item['max_error_reduction']:.8g} | {item['mean_absolute_error_reduction']:.8g} |")
    (output_dir / "paired_learning_curve_96_to_112.md").write_text("\n".join(lines) + "\n")
    return report
