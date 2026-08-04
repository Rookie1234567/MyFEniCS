"""Independent deterministic replay checker for Task006 M2R.

The checker does not call ``run_m2r`` or import its fitting helper.  It reads
only the immutable train37 arrays and uses separate scalar-model orchestration
to replay the selected candidate, then recomputes fold identity, transforms,
OOF predictions, metrics and the S0-authoritative S1 ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np

from surrogate.models import ExactARDGP, OrthogonalPCE, TrendResidualGP
from surrogate.task006.dataset import EPSILON
from surrogate.task006.design import (
    ANGLES,
    BLIND_GEOMETRIES,
    FORWARD_SOLVER_SHA,
    TASK005_LOCK,
    TASK006_DATASET_ID,
    canonical_hash,
    file_hash,
)


CANDIDATES = (
    "legendre_2", "legendre_3", "legendre_4", "local_rbf_k8",
    "matern52_ard_exact_gp", "degree2_trend_plus_matern52_residual",
)
FEATURE_MIN = np.asarray([115.0, 16.0])
FEATURE_MAX = np.asarray([125.0, 18.0])
N1_FLOOR = 1.0e-4


def scale(values: np.ndarray) -> np.ndarray:
    return 2.0 * (np.asarray(values, dtype=np.float64) - FEATURE_MIN) / (FEATURE_MAX - FEATURE_MIN) - 1.0


def sigma(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    return np.sqrt((0.01 * np.abs(values)) ** 2 + N1_FLOOR ** 2)


class ReplayScalar:
    def __init__(self, candidate: str, seed: int):
        self.candidate = candidate
        self.seed = int(seed)
        self.model: Any = None
        self.trend: Any = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> "ReplayScalar":
        if self.candidate.startswith("legendre_"):
            self.degree = int(self.candidate.split("_")[1])
            self.indices = [powers for powers in itertools.product(range(self.degree + 1), repeat=2)
                            if sum(powers) <= self.degree]
            design = self._basis(x)
            lhs = design.T @ design + 1.0e-10 * np.eye(design.shape[1])
            self.coefficients = np.linalg.solve(lhs, design.T @ np.asarray(y, dtype=np.float64))
        elif self.candidate == "local_rbf_k8":
            self.x_train = np.asarray(x, dtype=np.float64)
            self.y_train = np.asarray(y, dtype=np.float64)
        elif self.candidate == "matern52_ard_exact_gp":
            self.model = ExactARDGP(jitter=1.0e-10, optimizer_restarts=8,
                                    random_state=self.seed, normalize_y=True).fit(x, y)
        elif self.candidate == "degree2_trend_plus_matern52_residual":
            self.trend = OrthogonalPCE(degree=2, kind="legendre").fit(x, y)
            residual = np.asarray(y, dtype=np.float64) - self.trend.predict(x)
            self.model = ExactARDGP(jitter=1.0e-10, optimizer_restarts=8,
                                    random_state=self.seed, normalize_y=True).fit(x, residual)
        else:
            raise ValueError(candidate)
        return self

    def _basis(self, x: np.ndarray) -> np.ndarray:
        values = np.asarray(x, dtype=np.float64)
        columns = []
        for powers in self.indices:
            term = np.ones(len(values), dtype=np.float64)
            for axis, order in enumerate(powers):
                coeff = np.zeros(order + 1)
                coeff[-1] = 1.0
                term *= np.polynomial.legendre.legval(values[:, axis], coeff)
            columns.append(term)
        return np.column_stack(columns)

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        query = np.asarray(x, dtype=np.float64)
        if self.candidate.startswith("legendre_"):
            mean = self._basis(query) @ self.coefficients
            residual = self._basis(self._training_x) @ self.coefficients - self._training_y if hasattr(self, "_training_x") else np.zeros(2)
            std = np.full(len(query), max(float(np.std(residual, ddof=1)), 1.0e-8))
            return mean, std
        if self.candidate == "local_rbf_k8":
            values = np.empty(len(query), dtype=np.float64)
            for i, row in enumerate(query):
                distances = np.linalg.norm(self.x_train - row, axis=1)
                order = np.argsort(distances, kind="mergesort")[:min(8, len(distances))]
                local = distances[order]
                bandwidth = max(float(local[-1]), 1.0e-6)
                weights = np.exp(-(local / bandwidth) ** 2) + 1.0e-10
                weights /= np.sum(weights)
                values[i] = float(np.dot(weights, self.y_train[order]))
            return values, np.full(len(query), 1.0e-8)
        if self.candidate == "degree2_trend_plus_matern52_residual":
            mean, std = self.model.predict(query, return_std=True)
            return self.trend.predict(query) + mean, np.maximum(np.asarray(std), 1.0e-10)
        mean, std = self.model.predict(query, return_std=True)
        return np.asarray(mean), np.maximum(np.asarray(std), 1.0e-10)


def fit_scalar(candidate: str, x_train: np.ndarray, y_train: np.ndarray,
               x_query: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray, ReplayScalar]:
    model = ReplayScalar(candidate, seed)
    # Polynomial residual uncertainty needs the training rows; retain them
    # only inside the replay object and never use test truth.
    model._training_x = np.asarray(x_train, dtype=np.float64)
    model._training_y = np.asarray(y_train, dtype=np.float64)
    model.fit(x_train, y_train)
    mean, std = model.predict(x_query)
    return mean, np.maximum(std, 1.0e-10), model


def replay_contract(candidate: str, geometry: np.ndarray, latent: np.ndarray,
                    fractions: np.ndarray, train: np.ndarray,
                    query: np.ndarray, seed: int) -> dict[str, np.ndarray]:
    x_train = scale(geometry[train])
    x_query = scale(query)
    n = len(query)
    latent_mean = np.empty((n, 3, 2)); latent_std = np.empty_like(latent_mean)
    fraction_mean = np.empty((n, 3, 2)); fraction_std = np.empty_like(fraction_mean)
    aggregate_models = []; fraction_models = []
    for angle in range(3):
        for target in range(2):
            mean, std, model = fit_scalar(candidate, x_train, latent[train, angle, target], x_query,
                                          seed + angle * 11 + target)
            latent_mean[:, angle, target] = mean; latent_std[:, angle, target] = std
            aggregate_models.append(model)
            logits = np.log((fractions[train, angle, target, 0] + EPSILON)
                            / (fractions[train, angle, target, 1] + EPSILON))
            mean, std, model = fit_scalar(candidate, x_train, logits, x_query,
                                          seed + 200 + angle * 11 + target)
            fraction = 1.0 / (1.0 + np.exp(-np.clip(mean, -60.0, 60.0)))
            fraction_mean[:, angle, target] = fraction
            fraction_std[:, angle, target] = np.maximum(std * fraction * (1.0 - fraction), 1.0e-10)
            fraction_models.append(model)
    logits = np.concatenate([latent_mean, np.zeros((n, 3, 1))], axis=2)
    logits -= np.max(logits, axis=2, keepdims=True)
    weights = np.exp(logits)
    aggregate = weights / np.sum(weights, axis=2, keepdims=True)
    aggregate_std = np.maximum(np.max(latent_std, axis=2, keepdims=True) * np.ones_like(aggregate), 1.0e-10)
    side = aggregate[:, :, :2]
    side_std = aggregate_std[:, :, :2]
    selected = side * fraction_mean
    other = side * (1.0 - fraction_mean)
    selected_std = np.sqrt((fraction_mean * side_std) ** 2 + (side * fraction_std) ** 2)
    return {
        "aggregate": aggregate, "aggregate_std": aggregate_std,
        "side": side, "selected": selected, "selected_std": selected_std,
        "other": other, "other_std": np.sqrt(((1.0 - fraction_mean) * side_std) ** 2 + (side * fraction_std) ** 2),
        "ledger": selected + other - side,
    }


def array_hash(value: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(value, dtype=np.float64))
    descriptor = json.dumps({"dtype": str(array.dtype), "shape": list(array.shape)},
                            sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(descriptor + array.tobytes(order="C")).hexdigest()


def metric(truth: np.ndarray, prediction: np.ndarray, std: np.ndarray, mask: np.ndarray | None = None) -> dict[str, Any]:
    truth = np.asarray(truth, dtype=np.float64); prediction = np.asarray(prediction, dtype=np.float64)
    std = np.asarray(std, dtype=np.float64)
    if mask is not None:
        truth, prediction, std = truth[mask], prediction[mask], std[mask]
    error = prediction - truth
    scale_value = float(np.ptp(truth)) or 1.0
    normalized = np.abs(error) / sigma(truth)
    half_width = 1.96 * np.maximum(std, 1.0e-10)
    return {"n": int(error.size), "nrmse": float(np.sqrt(np.mean(error ** 2)) / scale_value),
            "p95_abs": float(np.percentile(np.abs(error), 95)), "max_abs": float(np.max(np.abs(error)),),
            "p95_normalized_N1": float(np.percentile(normalized, 95)), "max_normalized_N1": float(np.max(normalized)),
            "coverage_95": float(np.mean(np.abs(error) <= half_width)),
            "p95_half_width": float(np.percentile(half_width, 95)),
            "p95_N1_sigma": float(np.percentile(sigma(truth), 95)),
            "finite_positive_width": bool(np.all(np.isfinite(half_width)) and np.all(half_width > 0.0))}


def compare_metric(actual: dict[str, Any], expected: dict[str, Any], tolerance: float = 1.0e-10) -> bool:
    numeric = ("nrmse", "p95_abs", "max_abs", "p95_normalized_N1", "max_normalized_N1",
               "coverage_95", "p95_half_width", "p95_N1_sigma")
    return all(abs(float(actual[key]) - float(expected[key])) <= tolerance for key in numeric) and all(
        actual[key] == expected[key] for key in ("n", "finite_positive_width"))


def check(root: Path) -> tuple[dict[str, bool], list[str]]:
    outcomes = root / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes"
    dataset_root = root / "benchmarks/artifacts/cases/137_task006_train37_dataset/train37"
    errors: list[str] = []
    checks: dict[str, bool] = {}
    try:
        manifest = json.loads((dataset_root / "dataset_manifest.json").read_text())
        folds = json.loads((outcomes / "TRAIN37_GEOMETRY_FOLDS.json").read_text())
        comparison = json.loads((outcomes / "TRAIN37_MODEL_COMPARISON_V2.json").read_text())
        oof = json.loads((outcomes / "TRAIN37_OOF_PREDICTIONS_V2.json").read_text())
        ledger = json.loads((outcomes / "TRAIN37_S1_LEDGER_V2.json").read_text())
        selection = json.loads((outcomes / "TRAINING_MODEL_SELECTION_CANDIDATE_V2.json").read_text())
        recovery = json.loads((outcomes / "TRAIN37_SYNTHETIC_RECOVERY_V2.json").read_text())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"required_outputs": False}, [f"read failed: {exc}"]
    checks["required_outputs"] = True
    geometries = np.asarray(np.load(dataset_root / "geometries.npy"), dtype=np.float64)
    aggregates = np.asarray(np.load(dataset_root / "aggregates.npy")[:, :, :3], dtype=np.float64)
    latent = np.asarray(np.load(dataset_root / "aggregate_latent.npy"), dtype=np.float64)
    fractions = np.asarray(np.load(dataset_root / "s1_fractions.npy"), dtype=np.float64)
    selected_truth = np.asarray(np.load(dataset_root / "s1_selected_powers.npy"), dtype=np.float64)
    checks["dataset_identity"] = bool(manifest.get("dataset_id") == TASK006_DATASET_ID
                                      and manifest.get("forward_solver_sha") == FORWARD_SOLVER_SHA
                                      and manifest.get("blind_response_accessed") is False
                                      and file_hash(root / TASK005_LOCK) == "065dff4bf85722ca43af368e427708d1da78d5fae0178f7967c094b005ff12c3")
    expected_latent = np.stack((np.log((aggregates[:, :, 0] + EPSILON) / (aggregates[:, :, 2] + EPSILON)),
                                np.log((aggregates[:, :, 1] + EPSILON) / (aggregates[:, :, 2] + EPSILON))), axis=2)
    expected_fraction = np.stack((selected_truth / np.maximum(aggregates[:, :, :2], EPSILON),
                                  1.0 - selected_truth / np.maximum(aggregates[:, :, :2], EPSILON)), axis=3)
    checks["truth_transform_replay"] = bool(np.max(np.abs(expected_latent - latent)) <= 1.0e-12
                                             and np.max(np.abs(expected_fraction - fractions)) <= 1.0e-12)
    expected_folds = []
    for fold in range(5):
        test = [i for i in range(37) if i % 5 == fold]
        train = [i for i in range(37) if i % 5 != fold]
        expected_folds.append({
            "fold": fold, "train_indices": train, "test_indices": test,
            "train_geometries": geometries[train].tolist(), "test_geometries": geometries[test].tolist(),
            "test_region_counts": {
                "boundary": int(sum(geometries[i, 0] in (115.0, 125.0) or geometries[i, 1] in (16.0, 18.0) for i in test)),
                "interior": int(sum(not (geometries[i, 0] in (115.0, 125.0) or geometries[i, 1] in (16.0, 18.0)) for i in test)),
            },
        })
    expected_fold_hashes = []
    for row in expected_folds:
        expected_fold_hashes.append(canonical_hash({"fold": row["fold"], "train": row["train_geometries"], "test": row["test_geometries"]}))
    checks["fold_identity_frozen"] = bool(folds.get("folds") == [{**row, "fold_tuple_sha256": value} for row, value in zip(expected_folds, expected_fold_hashes)]
                                             and folds.get("folds_sha256") == canonical_hash(folds.get("folds"))
                                             and folds.get("all_test_indices_once") is True)
    selected_name = selection.get("selected_candidate")
    checks["selection_training_only"] = bool(selected_name in CANDIDATES
                                               and selection.get("training_only") is True
                                               and selection.get("status") == "m2r_training_qualified_pending_lock"
                                               and selection.get("blind_response_accessed") is False)
    checks["fixed_candidate_set"] = bool(set(comparison.get("candidates", {})) == set(CANDIDATES))

    if selected_name not in CANDIDATES:
        return checks, ["selected candidate not in fixed set"]
    replay_s0 = np.full((37, 3, 3), np.nan); replay_s0_std = np.full_like(replay_s0, np.nan)
    replay_side = np.full((37, 3, 2), np.nan); replay_selected = np.full_like(replay_side, np.nan)
    replay_selected_std = np.full_like(replay_side, np.nan); replay_other = np.full_like(replay_side, np.nan)
    replay_ledger = np.full_like(replay_side, np.nan)
    for fold, row in enumerate(expected_folds):
        test = np.asarray(row["test_indices"], dtype=np.int64)
        replay = replay_contract(selected_name, geometries, latent, fractions,
                                 np.asarray(row["train_indices"], dtype=np.int64), geometries[test],
                                 700 + fold * 97)
        replay_s0[test] = replay["aggregate"]; replay_s0_std[test] = replay["aggregate_std"]
        replay_side[test] = replay["side"]; replay_selected[test] = replay["selected"]
        replay_selected_std[test] = replay["selected_std"]; replay_other[test] = replay["other"]
        replay_ledger[test] = replay["ledger"]
    replay_hash = array_hash(np.concatenate((replay_s0, replay_side, replay_selected, replay_other, replay_ledger), axis=2))
    checks["selected_prediction_hash_replay"] = bool(replay_hash == selection.get("selected_prediction_hash")
                                                     == comparison["candidates"][selected_name].get("prediction_hash"))
    checks["composition_recomputed"] = bool(np.max(np.abs(np.sum(replay_s0, axis=2) - 1.0)) <= 1.0e-12)
    checks["ledger_recomputed"] = bool(np.max(np.abs(replay_ledger)) <= 1.0e-12
                                        and np.min(replay_selected) >= 0.0
                                        and np.min(replay_other) >= 0.0
                                        and np.all(replay_selected <= replay_side + 1.0e-12))
    checks["oof_row_count_and_folds"] = bool(len(oof.get("records", [])) == 37 * 3 * 5
                                              and all(0 <= int(row.get("fold", -1)) < 5 for row in oof.get("records", []))
                                              and all(int(row.get("geometry_index", -1)) in range(37) for row in oof.get("records", [])))
    ledger_rows = ledger.get("records", [])
    checks["ledger_records_complete"] = bool(len(ledger_rows) == 37 * 3 * 2
                                              and ledger.get("side_total_authority") == "S0 predicted R_total/T_total"
                                              and max(abs(float(row["ledger_residual"])) for row in ledger_rows) <= 1.0e-12)
    candidate = comparison["candidates"][selected_name]
    regions = ["boundary" if h in (115.0, 125.0) or w in (16.0, 18.0) else "interior" for h, w in geometries]
    recomputed_s0 = {f"A{angle}_{name}": metric(aggregates[:, angle, target], replay_s0[:, angle, target], replay_s0_std[:, angle, target])
                     for angle in range(3) for target, name in enumerate(("R_total", "T_total", "A_balance"))}
    recomputed_s1 = {f"A{angle}_{name}": metric(selected_truth[:, angle, target], replay_selected[:, angle, target], replay_selected_std[:, angle, target])
                     for angle in range(3) for target, name in enumerate(("reflection_m0_total", "transmission_m0_total"))}
    checks["metrics_recomputed"] = bool(all(compare_metric(recomputed_s0[key], candidate["s0_metrics"][key]) for key in recomputed_s0)
                                         and all(compare_metric(recomputed_s1[key], candidate["s1_metrics"][key]) for key in recomputed_s1))
    checks["selected_cv_and_recovery_gate"] = bool(candidate.get("hard_gate") is True
                                                    and recovery.get("hard_gate") is True
                                                    and recovery.get("summary", {}).get("rejected_count") == 0)
    checks["no_blind_or_validation"] = bool(selection.get("blind_response_accessed") is False
                                             and comparison.get("blind_response_accessed") is False
                                             and oof.get("blind_response_accessed") is False)
    if not all(checks.values()):
        errors.extend(f"failed:{key}" for key, value in checks.items() if not value)
    return checks, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "records/case139_check.json")
    args = parser.parse_args()
    checks, errors = check(args.root.resolve())
    result = {
        "schema_version": "task006.case139-m2r-replay-check.v1",
        "status": "pass" if all(checks.values()) else "failed",
        "checks": checks, "errors": errors, "training_only": True,
        "blind_response_accessed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
