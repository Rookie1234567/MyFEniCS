"""Independent Case130 checker for M4I.

This checker does not import ``src.surrogate.angle.m4i``.  It uses the compact
OOF rows to rebuild S1 arithmetic, source-only threshold candidates, the
highest-acceptance selection, accepted-source conformal radii, metrics and
response-blind design hashes.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
TRAIN = REPO / "benchmarks/artifacts/cases/127_task004_active_learning_round1/train112"
OUT = REPO / "surrogate_tasks/task004_nominal_geometry_angle_surrogate/outcomes"
FOLDS = OUT / "TRAIN112_LOCAL_REFERENCE_FOLDS.json"
BASE_OOF = OUT / "TRAIN112_LOCAL_OOF.json"
OOF = OUT / "SELECTIVE_OOF_V2.json"
THRESHOLD = OUT / "SELECTIVE_THRESHOLD_CORRECTION.json"
CONFORMAL = OUT / "SELECTIVE_CONDITIONAL_CONFORMAL.json"
COMPARISON = OUT / "SELECTIVE_MODEL_COMPARISON_V2.json"
ACCEPTANCE = OUT / "SELECTIVE_ACCEPTANCE_DOMAIN_V2.json"
WINDOWS = OUT / "SUPPORTED_INTERPOLATION_WINDOWS_V3.json"
POOL = REPO / "benchmarks/cases/123_task004_nominal_geometry_angle_surrogate/candidate_pool.json"
BLIND = REPO / "benchmarks/cases/123_task004_nominal_geometry_angle_surrogate/frozen_validation_design.json"
LOCK = OUT / "ANGLE_AGGREGATE_SELECTIVE_MODEL_SELECTION_LOCK.json"
RECORD = ROOT / "records/case130_check.json"

DATASET_ID = "task004_angle_nominal_p5_ny4_train112_v1"
FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
PREDICTORS = ("L2_local_matern_k24", "E1_latent_median_ensemble")
RULE = "S1_pre_frozen_m4e2_ensemble"
TARGETS = ("R_total", "T_total", "A_balance")
QUANTILES = (0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
WEIGHTS = {"native_std": 0.35, "matern_k24_k32_disagreement": 0.25,
           "rbf_matern_disagreement": 0.20, "nearest_training_distance": 0.10,
           "cutoff_topology_bonus": 0.10}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                         allow_nan=False).encode()).hexdigest()


def metrics(truth: np.ndarray, prediction: np.ndarray) -> dict[str, float | int]:
    if len(truth) == 0:
        return {"n": 0, "nrmse": float("inf"), "p95_abs": float("inf"), "max_abs": float("inf")}
    error = prediction - truth
    scale = float(np.ptp(truth)) or 1.0
    return {"n": int(error.size), "nrmse": float(np.sqrt(np.mean(error ** 2)) / scale),
            "p95_abs": float(np.percentile(np.abs(error), 95)),
            "max_abs": float(np.max(np.abs(error)))}


def metric_all(truth: np.ndarray, prediction: np.ndarray, indices: list[int]) -> dict[str, dict]:
    idx = np.asarray(indices, dtype=np.int64)
    return {target: metrics(truth[idx, i], prediction[idx, i])
            for i, target in enumerate(TARGETS)}


def point_gate(values: dict[str, dict]) -> bool:
    return bool(values and all(item["nrmse"] <= 0.01 and item["p95_abs"] <= 0.01 and
                               item["max_abs"] <= 0.03 for item in values.values()))


def supported_indices() -> dict[str, set[int]]:
    payload = json.loads(WINDOWS.read_text())
    return {item["name"]: {int(row["index"]) for row in item.get("support_rows", [])
                            if row.get("classification") != "unsupported_extrapolation"}
            for item in payload.get("windows", [])}


def supported_gate(accepted: set[int], truth: np.ndarray, prediction: np.ndarray) -> bool:
    windows = supported_indices()
    populated = []
    for indices in windows.values():
        selected = sorted(indices & accepted)
        if not selected:
            continue
        values = metric_all(truth, prediction, selected)
        populated.append(values)
    return bool(populated and all(all(item["p95_abs"] <= 0.02 for item in values.values())
                                  for values in populated))


def finite_conformal(values: np.ndarray) -> float:
    values = np.sort(np.asarray(values, dtype=float))
    level = min(1.0, math.ceil((len(values) + 1) * 0.95) / len(values))
    return float(np.quantile(values, level, method="higher"))


def quantile_bounds(values: np.ndarray) -> list[float]:
    values = np.asarray(values, dtype=float).reshape(-1)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return [0.0, 1.0]
    low, high = float(np.percentile(values, 5)), float(np.percentile(values, 95))
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        high = low + 1.0
    return [low, high]


def scale(values: np.ndarray, bounds: list[float]) -> np.ndarray:
    low, high = float(bounds[0]), float(bounds[1])
    return np.clip((np.asarray(values, dtype=float) - low) / max(high - low, 1.0e-15), 0.0, 1.0)


def rebuild_s1_risk(rows: list[dict], source: list[int]) -> tuple[np.ndarray, dict]:
    """Rebuild raw S1 risk and its fold-local normalization independently."""
    keys = ("native_std", "rbf_matern_disagreement", "matern_k24_k32_disagreement",
            "nearest_training_distance", "cutoff_risk", "topology_risk")
    raw = {key: np.asarray([row["risk_inputs"][key] for row in rows], dtype=float)
           for key in keys}
    boundary = np.asarray([row["risk_inputs"]["boundary_risk"] for row in rows], dtype=float)
    bounds = {}
    scaled = {}
    for key in keys:
        if raw[key].ndim == 1:
            bounds[key] = quantile_bounds(raw[key][source])
            scaled[key] = scale(raw[key], bounds[key])
        else:
            bounds[key] = [quantile_bounds(raw[key][source, i]) for i in range(raw[key].shape[1])]
            scaled[key] = np.column_stack([scale(raw[key][:, i], bounds[key][i])
                                           for i in range(raw[key].shape[1])])
    geometry = np.clip(0.5 * scaled["cutoff_risk"][:, None] +
                       0.35 * scaled["topology_risk"][:, None] +
                       0.15 * boundary[:, None], 0.0, 1.0)
    risk = np.max(0.35 * scaled["native_std"] +
                  0.25 * scaled["matern_k24_k32_disagreement"] +
                  0.20 * scaled["rbf_matern_disagreement"] +
                  0.10 * scaled["nearest_training_distance"][:, None] +
                  0.10 * geometry, axis=1)
    return risk, bounds


def design_angles(path: Path) -> np.ndarray:
    payload = json.loads(path.read_text())
    return np.asarray([[float(row["grazing_deg"]), float(row["azimuth_deg"])]
                       for row in payload["points"]], dtype=float)


def main() -> int:
    checks: dict[str, bool] = {}
    errors: list[str] = []
    required = [TRAIN / "dataset_manifest.json", TRAIN / "file_hashes.json", TRAIN / "aggregates.npy",
                FOLDS, BASE_OOF, OOF, THRESHOLD, CONFORMAL, COMPARISON, ACCEPTANCE, WINDOWS, POOL, BLIND]
    checks["required_artifacts_present"] = all(path.is_file() for path in required)
    if not checks["required_artifacts_present"]:
        errors.append("a required M4I artifact is missing")
        return write_result(checks, errors)
    manifest = json.loads((TRAIN / "dataset_manifest.json").read_text())
    expected_hashes = json.loads((TRAIN / "file_hashes.json").read_text())
    actual_hashes = {path.name: digest(path) for path in sorted(TRAIN.iterdir())
                     if path.is_file() and path.name != "file_hashes.json"}
    checks["immutable_train112_identity"] = bool(actual_hashes == expected_hashes and
        manifest.get("dataset_id") == DATASET_ID and manifest.get("training_count") == 112 and
        manifest.get("forward_solver_sha") == FORWARD_SHA and manifest.get("validation_target_accessed") is False)

    folds_payload = json.loads(FOLDS.read_text())
    fold_for: dict[int, int] = {}
    folds_ok = len(folds_payload.get("folds", [])) == 5
    for item in folds_payload.get("folds", []):
        fold = int(item["fold"]); train = [int(x) for x in item["train_indices"]]; test = [int(x) for x in item["test_indices"]]
        folds_ok = folds_ok and not set(train) & set(test)
        folds_ok = folds_ok and item.get("fold_sha256") == canonical({"fold": fold,
            "train_indices": train, "test_indices": test, "test_tuples": item["test_tuples"]})
        for index in test:
            folds_ok = folds_ok and index not in fold_for
            fold_for[index] = fold
    checks["frozen_folds_each_index_once"] = bool(folds_ok and sorted(fold_for) == list(range(112)))

    comparison = json.loads(COMPARISON.read_text())
    threshold_payload = json.loads(THRESHOLD.read_text())
    conformal_payload = json.loads(CONFORMAL.read_text())
    acceptance_payload = json.loads(ACCEPTANCE.read_text())
    code_sha = comparison.get("surrogate_training_code_sha")
    checks["source_identity_and_candidate_contract"] = bool(
        comparison.get("dataset_id") == DATASET_ID and comparison.get("forward_solver_sha") == FORWARD_SHA and
        tuple(comparison.get("candidate_set", [])) == PREDICTORS and comparison.get("risk_rule_set") == [RULE] and
        threshold_payload.get("surrogate_training_code_sha") == code_sha and
        conformal_payload.get("surrogate_training_code_sha") == code_sha and
        acceptance_payload.get("surrogate_training_code_sha") == code_sha and
        code_sha and code_sha != "WORKTREE_M4I")

    selective = json.loads(OOF.read_text())
    base = json.loads(BASE_OOF.read_text())
    rows_all = selective.get("records", {})
    crossfit_ok = selective.get("dataset_id") == DATASET_ID and selective.get("validation_response_accessed") is False
    for predictor in PREDICTORS:
        rows = rows_all.get(predictor, [])
        crossfit_ok = crossfit_ok and len(rows) == 112 and sorted(int(row["sample_index"]) for row in rows) == list(range(112))
        if len(rows) != 112:
            continue
        truth = np.asarray([row["truth"] for row in rows], dtype=float)
        prediction = np.asarray([row["prediction"] for row in rows], dtype=float)
        thresholds = threshold_payload["predictor_results"][predictor]["folds"]
        reported_result = comparison["results"][predictor]
        accepted_indices: list[int] = []
        radii = np.full((112, 3), np.nan)
        for fold_item in thresholds:
            fold = int(fold_item["fold"])
            source = [i for i in range(112) if fold_for[i] != fold]
            test = [i for i in range(112) if fold_for[i] == fold]
            fold_risk, rebuilt_bounds = rebuild_s1_risk(rows, source)
            stored_bounds = fold_item.get("normalization_bounds", {})
            for key, value in rebuilt_bounds.items():
                crossfit_ok = crossfit_ok and np.allclose(np.asarray(stored_bounds.get(key), dtype=float),
                                                          np.asarray(value, dtype=float), atol=1.0e-12, rtol=0.0)
            crossfit_ok = crossfit_ok and np.allclose(
                np.asarray([rows[i]["risk_score"] for i in test], dtype=float),
                fold_risk[test], atol=1.0e-12, rtol=0.0)
            threshold_info = fold_item["threshold"]
            candidates = threshold_info["candidate_grid"]
            passing = []
            for candidate in candidates:
                q = float(candidate["quantile"])
                threshold = float(np.quantile(fold_risk[source], q, method="linear"))
                source_accept = [i for i in source if float(fold_risk[i]) <= threshold + 1.0e-15]
                values = metric_all(truth, prediction, source_accept)
                accuracy = point_gate(values)
                support = supported_gate(set(source_accept), truth, prediction)
                composition = bool(source_accept and np.max(np.abs(np.sum(prediction[source_accept], axis=1) - 1.0)) <= 1.0e-12)
                source_gate = bool(len(source_accept) / len(source) >= 0.70 and accuracy and support and composition)
                expected = {"quantile": q, "threshold": threshold, "accepted_count": len(source_accept),
                            "accepted_fraction": len(source_accept) / len(source), "metrics": values,
                            "accepted_indices": source_accept,
                            "accuracy_gate": accuracy, "supported_window_gate": support,
                            "composition_gate": composition, "source_gate": source_gate}
                # Stored candidate grids may contain the detailed window rows;
                # these scalar fields are the independent authority here.
                crossfit_ok = crossfit_ok and candidate.get("quantile") == q and \
                    abs(float(candidate.get("threshold")) - threshold) <= 1.0e-12 and \
                    candidate.get("accepted_count") == expected["accepted_count"] and \
                    abs(float(candidate.get("accepted_fraction")) - expected["accepted_fraction"]) <= 1.0e-12 and \
                    candidate.get("accuracy_gate") == accuracy and candidate.get("supported_window_gate") == support and \
                    candidate.get("composition_gate") == composition and candidate.get("source_gate") == source_gate
                if source_gate:
                    passing.append((expected["accepted_fraction"], -max(max(item["nrmse"] / 0.01, item["p95_abs"] / 0.01,
                                                                         item["max_abs"] / 0.03) for item in values.values()),
                                    -threshold, -q, expected))
            selected = max(passing, key=lambda item: item[:4])[4] if passing else None
            stored_selected = threshold_info.get("selected")
            crossfit_ok = crossfit_ok and ((selected is None and stored_selected is None) or
                (selected is not None and stored_selected is not None and
                 abs(float(stored_selected["quantile"]) - selected["quantile"]) <= 1.0e-12 and
                 abs(float(stored_selected["threshold"]) - selected["threshold"]) <= 1.0e-12))
            crossfit_ok = crossfit_ok and bool(fold_item.get("no_fallback")) == (selected is not None)
            if selected is None:
                continue
            source_accept = np.asarray(selected["accepted_indices"], dtype=np.int64)
            radius = np.asarray([finite_conformal(np.abs(prediction[source_accept, i] - truth[source_accept, i]))
                                 for i in range(3)])
            radii[test] = radius[None, :]
            for index in test:
                row = rows[index]
                expected_accept = float(fold_risk[index]) <= selected["threshold"] + 1.0e-15
                crossfit_ok = crossfit_ok and bool(row["accepted"]) == expected_accept and \
                    row.get("threshold_source_folds") == fold_item.get("source_outer_folds") and \
                    row.get("threshold_source_indices_hash") == canonical(source) and \
                    row.get("threshold_source_gate") is True and row.get("response_used_for_acceptance") is False
                crossfit_ok = crossfit_ok and np.allclose(np.asarray(row["conformal_half_width"], dtype=float), radius,
                                                           atol=1.0e-12, rtol=0.0)
                if expected_accept:
                    accepted_indices.append(index)
        # Canonicalize the cross-fit accumulation order before comparing with
        # the compact record.  Fold test sets are disjoint but are not
        # required to be globally contiguous, so fold traversal order must not
        # become part of the evidence identity.
        accepted_indices = sorted(accepted_indices)
        reported_accept = [int(x) for x in reported_result.get("accepted_indices", [])]
        crossfit_ok = crossfit_ok and reported_accept == accepted_indices
        crossfit_ok = crossfit_ok and reported_result.get("accepted_indices_sha256") == canonical(accepted_indices)
        crossfit_ok = crossfit_ok and reported_result.get("rejected_indices") == [i for i in range(112) if i not in accepted_indices]
        values = metric_all(truth, prediction, accepted_indices)
        for target in TARGETS:
            for name in ("nrmse", "p95_abs", "max_abs"):
                crossfit_ok = crossfit_ok and abs(float(values[target][name]) - float(reported_result["metrics_accepted"][target][name])) <= 1.0e-10
        coverage = np.mean(np.abs(prediction[accepted_indices] - truth[accepted_indices]) <= radii[accepted_indices], axis=0) if accepted_indices else np.zeros(3)
        for i, target in enumerate(TARGETS):
            crossfit_ok = crossfit_ok and abs(float(coverage[i]) - float(reported_result["conditional_conformal"]["coverage"][target])) <= 1.0e-10
        crossfit_ok = crossfit_ok and reported_result.get("response_used_for_acceptance") is False
    checks["thresholds_no_fallback_highest_passing_quantile"] = bool(crossfit_ok)

    acceptance_ok = bool(acceptance_payload.get("response_blind") is True and
                         acceptance_payload.get("validation_response_accessed") is False)
    pool_angles = design_angles(POOL); blind_angles = design_angles(BLIND)
    for name, angles, count in (("candidate_pool", pool_angles, 4096), ("blind_design", blind_angles, 24)):
        domain = acceptance_payload.get(name) or {}
        for predictor in PREDICTORS:
            key = f"{predictor}::{RULE}"; item = domain.get(key, {})
            risk = np.asarray(item.get("risk_score", []), dtype=float)
            accepted = [int(x) for x in item.get("accepted_indices", [])]
            rejected = [int(x) for x in item.get("rejected_indices", [])]
            expected = np.flatnonzero(risk <= float(item.get("threshold", np.inf)) + 1.0e-15).astype(int).tolist()
            acceptance_ok = acceptance_ok and len(risk) == count and accepted == expected and \
                sorted(accepted + rejected) == list(range(count)) and \
                item.get("accepted_indices_sha256") == canonical(accepted) and \
                item.get("rejected_indices_sha256") == canonical(rejected) and \
                item.get("accepted_angle_tuple_sha256") == canonical(angles[accepted].round(12).tolist()) and \
                item.get("response_used_for_acceptance") is False
    checks["response_blind_candidate_and_blind_hashes"] = bool(acceptance_ok)

    checks["m4i_controlled_negative_no_lock_no_blind"] = bool(
        comparison.get("selected_candidate") is None and comparison.get("model_lock_created") is False and
        not LOCK.exists() and not (OUT / "blind24_preacceptance_manifest.json").exists() and
        not (REPO / "benchmarks/artifacts/cases/130_task004_selective_interval_correction").exists())
    checks["conditional_interval_contract"] = bool(
        conformal_payload.get("coverage_lower_bound") == 0.90 and
        conformal_payload.get("p95_half_width_upper_bound") == 0.02 and
        conformal_payload.get("max_half_width_upper_bound") == 0.03 and
        conformal_payload.get("old_coverage_upper_bound") == "warning_only" and
        conformal_payload.get("validation_response_accessed") is False)
    checks["all_checks"] = bool(all(checks.values()) and not errors)
    return write_result(checks, errors)


def write_result(checks: dict[str, bool], errors: list[str]) -> int:
    result = {"schema_version": "case130.check.v1",
              "status": "pass" if checks.get("all_checks", False) else "fail",
              "qualification_status": "controlled_negative",
              "checks": checks, "errors": errors, "dataset_id": DATASET_ID,
              "forward_solver_sha": FORWARD_SHA, "training_count": 112,
              "candidate_pool_count": 4096, "blind_design_count": 24,
              "validation_response_accessed": False, "new_fem_budget": 0,
              "model_lock_created": False, "blind_fem_run": False}
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
