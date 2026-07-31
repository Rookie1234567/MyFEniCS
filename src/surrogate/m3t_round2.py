"""Fixed-reference 96/104/112 learning curve after Round-2.

All three training sizes are evaluated on the same original-96 test rows and
with the same G1/G2 model contracts.  This is a training-domain diagnostic;
the frozen validation targets remain sealed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .dataset import CASE119_ROOT, load_training_dataset
from .folds import FOLD_SEED, folds
from .features import transform_feature_candidate
from .physics import reconstruct_aggregates
from .targets import aggregate_log_ratios
from .cv import _metrics, _regions
from .m3t import _fit_predict


ROUND1 = Path("benchmarks/artifacts/cases/121_task003_active_learning_round1_retry_cachefix/compact_dataset")
ROUND2 = Path("benchmarks/artifacts/cases/122_task003_round2/compact_dataset")
OUT = Path("surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/outcomes")


def _metric_block(truth: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    return {name: _metrics(truth[:, index], prediction[:, index])
            for index, name in enumerate(("R_total", "T_total", "A_balance"))}


def _run_family(old: Any, datasets: dict[int, Any], split: list[tuple[np.ndarray, np.ndarray]],
                family: str) -> dict[str, Any]:
    x_old = transform_feature_candidate(old.inputs, "B")
    y_old = aggregate_log_ratios(old.aggregates)
    truth = old.aggregates[:, :3]
    size_results: dict[str, Any] = {}
    predictions: dict[int, np.ndarray] = {}
    for size, dataset in datasets.items():
        x_all = transform_feature_candidate(dataset.inputs, "B")
        y_all = aggregate_log_ratios(dataset.aggregates)
        prediction = np.full((96, 3), np.nan, dtype=np.float64)
        std = np.full((96, 3), np.nan, dtype=np.float64)
        fold_rows = []
        for fold_index, (train, test) in enumerate(split):
            train_indices = np.arange(size, dtype=np.int64) if size > 96 else train
            if size > 96:
                train_indices = np.concatenate((train, np.arange(96, size, dtype=np.int64)))
            latent, latent_std, metadata = _fit_predict(
                family, x_all[train_indices], y_all[train_indices], x_old[test])
            prediction[test] = reconstruct_aggregates(latent)[:, :3]
            std[test] = np.column_stack((latent_std[:, 0], latent_std[:, 1], latent_std[:, 1]))
            fold_rows.append({"fold": fold_index, "test_indices": test.tolist(),
                              "train_count": int(train_indices.size), "fit": metadata})
        predictions[size] = prediction
        regions = _regions(old.inputs)
        breakdown = {}
        for region in sorted({name for row in regions for name in row}):
            selected = np.asarray([region in row for row in regions])
            breakdown[region] = {name: _metrics(truth[selected, i], prediction[selected, i])
                                 for i, name in enumerate(("R_total", "T_total", "A_balance"))}
        size_results[str(size)] = {"metrics": _metric_block(truth, prediction),
                                   "folds": fold_rows, "region_breakdown": breakdown}
    paired = []
    for row in range(96):
        fold = next(index for index, (_, test) in enumerate(split) if row in test)
        for index, name in enumerate(("R_total", "T_total", "A_balance")):
            base = abs(float(predictions[96][row, index] - truth[row, index]))
            e104 = abs(float(predictions[104][row, index] - truth[row, index]))
            e112 = abs(float(predictions[112][row, index] - truth[row, index]))
            paired.append({"sample_index": row, "fold": fold, "target": name,
                           "truth": float(truth[row, index]), "baseline96_abs_error": base,
                           "enriched104_abs_error": e104, "enriched112_abs_error": e112,
                           "delta104_vs96": e104 - base, "delta112_vs104": e112 - e104,
                           "delta112_vs96": e112 - base, "regions": _regions(old.inputs[row:row + 1])[0]})
    return {"family": family, "sizes": size_results, "paired_records": paired}


def run() -> dict[str, Any]:
    old = load_training_dataset(CASE119_ROOT)
    enriched104 = load_training_dataset(ROUND1)
    enriched112 = load_training_dataset(ROUND2)
    if (old.n_samples, enriched104.n_samples, enriched112.n_samples) != (96, 104, 112):
        raise RuntimeError("expected 96/104/112 training views")
    if not np.array_equal(old.inputs, enriched104.inputs[:96]) or not np.array_equal(old.inputs, enriched112.inputs[:96]):
        raise RuntimeError("original 96 rows changed")
    if not np.array_equal(enriched104.inputs, enriched112.inputs[:104]):
        raise RuntimeError("Round1 rows changed in Round2 dataset")
    split = folds(transform_feature_candidate(old.inputs, "B"), n_splits=5, seed=FOLD_SEED)
    families = [_run_family(old, {96: old, 104: enriched104, 112: enriched112}, split, family)
                for family in ("G1_constant_gp", "G2_degree2_trend_residual_gp")]
    result = {"schema_version": "task003.m3t-fixed-reference-learning-curve.v1",
              "validation_target_accessed": False, "reference_training_count": 96,
              "sizes": [96, 104, 112], "feature_candidate": "B", "fold_seed": FOLD_SEED,
              "families": families}
    (OUT / "LEARNING_CURVE_FIXED_REFERENCE.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = ["# Fixed-reference learning curve (training-only)", "",
             "The original 96 test rows and fold assignment are held fixed; this is not frozen validation.", ""]
    for family in families:
        lines += [f"## {family['family']}", "", "| training rows | R NRMSE | T NRMSE | A NRMSE |", "|---:|---:|---:|---:|"]
        for size in (96, 104, 112):
            m = family["sizes"][str(size)]["metrics"]
            lines.append(f"| {size} | {m['R_total']['nrmse']:.8g} | {m['T_total']['nrmse']:.8g} | {m['A_balance']['nrmse']:.8g} |")
        lines.append("")
    (OUT / "learning_curve_fixed_reference.md").write_text("\n".join(lines) + "\n")
    return result


if __name__ == "__main__":
    result = run()
    print(json.dumps({"status": "pass", "sizes": result["sizes"],
                      "validation_target_accessed": result["validation_target_accessed"]}, indent=2))
