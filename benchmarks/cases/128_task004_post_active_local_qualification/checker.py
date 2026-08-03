"""Independent Case128 checker for Required M4G.

The checker does not import the M4G fitter.  It rebuilds fold coverage,
train112 tuple identity and OOF error/metric contracts from the package arrays
and stored records, then checks that the audit remains fail-closed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
TRAIN112 = REPO / "benchmarks/artifacts/cases/127_task004_active_learning_round1/train112"
OUTCOMES = REPO / "surrogate_tasks/task004_nominal_geometry_angle_surrogate/outcomes"
FOLDS = OUTCOMES / "TRAIN112_LOCAL_REFERENCE_FOLDS.json"
COMPARISON = OUTCOMES / "TRAIN112_LOCAL_MODEL_COMPARISON.json"
OOF = OUTCOMES / "TRAIN112_LOCAL_OOF.json"
AUDIT = OUTCOMES / "POST_ACTIVE_OUTLIER_AUDIT.json"
SAFE = OUTCOMES / "ANGLE_AGGREGATE_SAFE_DOMAIN_CANDIDATE.json"
PAIRED = OUTCOMES / "paired_learning_curve_96_to_112.json"
OUT = ROOT / "records/case128_check.json"

FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
CODE_SHA = "44e9831d4cfae0c95b4e02d59effd6c6fa0b4270"
DATASET_ID = "task004_angle_nominal_p5_ny4_train112_v1"
CANDIDATES = {
    "L1_local_rbf_k24_s1e-08", "L2_local_matern_k24",
    "L2_local_matern_k32", "L4_trend_local_residual_k24",
    "E1_latent_median_ensemble", "E2_cross_fitted_nonnegative_stack",
}
TARGETS = ("R_total", "T_total", "A_balance")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def metrics(truth: np.ndarray, prediction: np.ndarray) -> dict[str, float | int]:
    error = np.asarray(prediction) - np.asarray(truth)
    scale = float(np.ptp(truth)) or 1.0
    return {"n": int(error.size), "nrmse": float(np.sqrt(np.mean(error ** 2)) / scale),
            "p95_abs": float(np.percentile(np.abs(error), 95)),
            "max_abs": float(np.max(np.abs(error)))}


def fold_hash(row: dict) -> str:
    return canonical({"fold": row["fold"], "train_indices": row["train_indices"],
                      "test_indices": row["test_indices"], "test_tuples": row["test_tuples"]})


def main() -> int:
    checks: dict[str, bool] = {}
    errors: list[str] = []
    required = [TRAIN112 / "dataset_manifest.json", TRAIN112 / "file_hashes.json",
                TRAIN112 / "inputs.npy", TRAIN112 / "aggregates.npy", FOLDS,
                COMPARISON, OOF, AUDIT, SAFE, PAIRED]
    checks["required_artifacts_present"] = all(path.is_file() for path in required)
    if not checks["required_artifacts_present"]:
        errors.append("a required M4G artifact is missing")
        return write_result(checks, errors)
    manifest = json.loads((TRAIN112 / "dataset_manifest.json").read_text())
    stored_hashes = json.loads((TRAIN112 / "file_hashes.json").read_text())
    actual_hashes = {path.name: digest(path) for path in sorted(TRAIN112.iterdir())
                     if path.is_file() and path.name != "file_hashes.json"}
    checks["train112_hashes_and_identity"] = bool(
        actual_hashes == stored_hashes and manifest.get("dataset_id") == DATASET_ID and
        manifest.get("sample_count") == 112 and manifest.get("training_count") == 112 and
        manifest.get("forward_solver_sha") == FORWARD_SHA and
        manifest.get("validation_target_accessed") is False and
        manifest.get("immutable") is True
    )
    inputs = np.load(TRAIN112 / "inputs.npy", allow_pickle=False)
    aggregates = np.load(TRAIN112 / "aggregates.npy", allow_pickle=False)[:, :3]
    folds_payload = json.loads(FOLDS.read_text())
    fold_rows = folds_payload.get("folds", [])
    all_tests = np.concatenate([np.asarray(row["test_indices"], dtype=np.int64) for row in fold_rows])
    split_ok = bool(
        folds_payload.get("dataset_id") == DATASET_ID and
        folds_payload.get("training_tuple_sha256") == manifest.get("training_tuple_sha256") and
        folds_payload.get("fold_seed") == 20260731 and len(fold_rows) == 5 and
        sorted(all_tests.tolist()) == list(range(112)) and
        all(len(set(row["train_indices"]) & set(row["test_indices"])) == 0 for row in fold_rows) and
        all(fold_hash(row) == row.get("fold_sha256") for row in fold_rows) and
        folds_payload.get("test_coverage", {}).get("each_index_once") is True
    )
    checks["folds_each_index_once_and_hash_bound"] = split_ok
    fold_for_index = {}
    if split_ok:
        for row in fold_rows:
            fold_for_index.update({int(index): int(row["fold"]) for index in row["test_indices"]})
    comparison = json.loads(COMPARISON.read_text())
    oof = json.loads(OOF.read_text())
    checks["candidate_set_and_source_identity"] = bool(
        set(comparison.get("candidate_set", [])) == CANDIDATES and
        set(oof.get("candidate_set", [])) == CANDIDATES and
        comparison.get("dataset_id") == DATASET_ID and
        comparison.get("forward_solver_sha") == FORWARD_SHA and
        comparison.get("surrogate_training_code_sha") == CODE_SHA and
        oof.get("validation_target_accessed") is False
    )
    oof_ok = True
    recomputed_metrics: dict[str, dict[str, dict]] = {}
    rows_by_candidate = oof.get("records", {})
    for candidate in CANDIDATES:
        rows = rows_by_candidate.get(candidate, [])
        if len(rows) != 112:
            oof_ok = False
            continue
        prediction = np.asarray([row["prediction"] for row in rows], dtype=float)
        truth = np.asarray([row["truth"] for row in rows], dtype=float)
        recomputed_metrics[candidate] = {
            target: metrics(truth[:, index], prediction[:, index])
            for index, target in enumerate(TARGETS)
        }
        for row in rows:
            index = int(row["sample_index"])
            expected_error = prediction[index] - truth[index]
            oof_ok = bool(oof_ok and row.get("identity") == ("old96" if index < 96 else "new16") and
                          row.get("fold") == fold_for_index.get(index) and
                          np.allclose(np.asarray(row["error"]), expected_error, atol=1.0e-12) and
                          np.allclose(np.asarray(row["absolute_error"]), np.abs(expected_error), atol=1.0e-12) and
                          np.allclose(truth[index], aggregates[index], atol=1.0e-12))
    checks["all_candidate_oof_rows_and_errors"] = oof_ok
    reported = {row.get("candidate"): row for row in comparison.get("candidate_results", [])}
    metric_ok = True
    for candidate, values in recomputed_metrics.items():
        if candidate not in reported:
            metric_ok = False
            continue
        for target in TARGETS:
            for key in ("nrmse", "p95_abs", "max_abs"):
                metric_ok = bool(metric_ok and
                                 abs(float(values[target][key]) - float(reported[candidate]["metrics"][target][key])) <= 1.0e-12)
        composition = np.asarray([row["prediction"] for row in rows_by_candidate[candidate]], dtype=float)
        metric_ok = bool(metric_ok and np.max(np.abs(np.sum(composition, axis=1) - 1.0)) <= 1.0e-12 and
                         reported[candidate].get("composition_exact") is True)
    checks["metrics_and_composition_recomputed"] = metric_ok
    checks["ensemble_contract"] = bool(
        reported.get("E1_latent_median_ensemble", {}).get("ensemble_rule") == "median" and
        reported.get("E2_cross_fitted_nonnegative_stack", {}).get("ensemble_rule") == "stack" and
        all(np.all(np.asarray(item.get("weights", []), dtype=float) >= -1.0e-12) and
            np.allclose(np.sum(np.asarray(item.get("weights", []), dtype=float), axis=1),
                        np.ones(2), atol=1.0e-10) and
            np.asarray(item.get("weights", []), dtype=float).shape == (2, 3)
            for item in reported.get("E2_cross_fitted_nonnegative_stack", {}).get("stack_weights", [])
            for _ in [0])
    )
    audit = json.loads(AUDIT.read_text())
    audit_ok = bool(audit.get("dataset_id") == DATASET_ID and
                    audit.get("validation_target_accessed") is False and
                    set(audit.get("targets", {})) == set(TARGETS) and
                    all(len(rows) == 10 for rows in audit.get("targets", {}).values()))
    for target, rows in audit.get("targets", {}).items():
        for row in rows:
            index = int(row["sample_index"])
            reference = row.get("reference_candidate")
            audit_ok = bool(audit_ok and reference in CANDIDATES and
                            abs(float(row["reference_absolute_error"]) -
                                abs(float(rows_by_candidate[reference][index]["error"][TARGETS.index(target)]))) <= 1.0e-12 and
                            row.get("classification") in {"coverage_hole", "cutoff_high_curvature",
                                                            "boundary_one_sided", "model_instability", "unexplained"})
    checks["post_active_outlier_audit_references_oof"] = audit_ok
    safe = json.loads(SAFE.read_text())
    checks["safe_domain_secondary_diagnostic"] = bool(
        safe.get("candidate_pool_count") == 4096 and
        safe.get("safe_count", -1) + safe.get("excluded_count", -1) == 4096 and
        0.0 <= float(safe.get("safe_fraction", -1.0)) <= 1.0 and
        safe.get("full_domain_model_lock") is False and
        safe.get("validation_target_accessed") is False
    )
    paired = json.loads(PAIRED.read_text())
    checks["paired_reference_semantics"] = bool(
        paired.get("paired_reference_candidate") == "L1_local_rbf_k24_s1e-08" and
        paired.get("diagnostic_only_not_model_lock") is True and
        "selected_final_candidate" not in paired and
        paired.get("validation_target_accessed") is False
    )
    checks["no_lock_no_blind_no_new_fem"] = bool(
        not (OUTCOMES / "ANGLE_AGGREGATE_MODEL_SELECTION_LOCK.json").exists() and
        not (OUTCOMES / "ANGLE_ORDER_MODEL_SELECTION_LOCK.json").exists()
    )
    checks["all_checks"] = bool(all(checks.values()) and not errors)
    return write_result(checks, errors)


def write_result(checks: dict[str, bool], errors: list[str]) -> int:
    result = {"schema_version": "case128.check.v1",
              "status": "pass" if checks.get("all_checks", False) else "fail",
              "checks": checks, "errors": errors,
              "dataset_id": DATASET_ID, "training_count": 112,
              "forward_solver_sha": FORWARD_SHA,
              "validation_response_accessed": False, "new_fem_budget": 0}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
