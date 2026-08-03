"""Independent checker for the M4H training-only selective contract.

The checker intentionally does not import ``src.surrogate.angle.m4h``.  It
recomputes hashes, fold exclusion, risk arithmetic, acceptance semantics and
accepted-set metrics from stored compact records.  A controlled-negative
qualification is a checker pass when the evidence itself is internally sound.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
TRAIN = REPO / "benchmarks/artifacts/cases/127_task004_active_learning_round1/train112"
OUTCOMES = REPO / "surrogate_tasks/task004_nominal_geometry_angle_surrogate/outcomes"
FOLDS = OUTCOMES / "TRAIN112_LOCAL_REFERENCE_FOLDS.json"
BASE_OOF = OUTCOMES / "TRAIN112_LOCAL_OOF.json"
OOF = OUTCOMES / "SELECTIVE_OOF.json"
COMPARISON = OUTCOMES / "SELECTIVE_MODEL_COMPARISON.json"
CROSSFIT = OUTCOMES / "SELECTIVE_RISK_CROSSFIT.json"
CONTRACT = OUTCOMES / "ANGLE_AGGREGATE_SELECTIVE_QUALIFICATION_CONTRACT.json"
ACCEPTANCE = OUTCOMES / "ANGLE_AGGREGATE_SELECTIVE_ACCEPTANCE_DOMAIN.json"
STRUCTURAL = OUTCOMES / "ANGLE_AGGREGATE_STRUCTURAL_SUPPORT_DOMAIN.json"
OUT = ROOT / "records/case129_check.json"

DATASET_ID = "task004_angle_nominal_p5_ny4_train112_v1"
FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
TARGETS = ("R_total", "T_total", "A_balance")
PREDICTORS = ("L1_local_rbf_k24_s1e-08", "L2_local_matern_k24", "E1_latent_median_ensemble")
RULES = ("S1_pre_frozen_m4e2_ensemble", "S2_std_disagreement_max")
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
    error = np.asarray(prediction) - np.asarray(truth)
    scale = float(np.ptp(truth)) or 1.0
    return {"n": int(error.size), "nrmse": float(np.sqrt(np.mean(error ** 2)) / scale),
            "p95_abs": float(np.percentile(np.abs(error), 95)),
            "max_abs": float(np.max(np.abs(error)))}


def metrics_all(truth: np.ndarray, prediction: np.ndarray, indices: list[int]) -> dict[str, dict]:
    idx = np.asarray(indices, dtype=np.int64)
    return {target: metrics(truth[idx, i], prediction[idx, i])
            for i, target in enumerate(TARGETS)}


def close(left: object, right: object, atol: float = 1.0e-10) -> bool:
    return bool(np.allclose(np.asarray(left, dtype=float), np.asarray(right, dtype=float),
                            atol=atol, rtol=0.0))


def main() -> int:
    checks: dict[str, bool] = {}
    errors: list[str] = []
    required = [TRAIN / "dataset_manifest.json", TRAIN / "file_hashes.json", TRAIN / "inputs.npy",
                TRAIN / "aggregates.npy", FOLDS, BASE_OOF, OOF, COMPARISON, CROSSFIT,
                CONTRACT, ACCEPTANCE, STRUCTURAL]
    checks["required_artifacts_present"] = all(path.is_file() for path in required)
    if not checks["required_artifacts_present"]:
        errors.append("a required M4H artifact is missing")
        return write_result(checks, errors)

    manifest = json.loads((TRAIN / "dataset_manifest.json").read_text())
    stored_hashes = json.loads((TRAIN / "file_hashes.json").read_text())
    actual_hashes = {path.name: digest(path) for path in sorted(TRAIN.iterdir())
                     if path.is_file() and path.name != "file_hashes.json"}
    checks["immutable_train112_identity"] = bool(
        actual_hashes == stored_hashes and manifest.get("dataset_id") == DATASET_ID and
        manifest.get("sample_count") == 112 and manifest.get("training_count") == 112 and
        manifest.get("forward_solver_sha") == FORWARD_SHA and
        manifest.get("validation_target_accessed") is False and manifest.get("immutable") is True
    )

    folds_payload = json.loads(FOLDS.read_text())
    fold_rows = folds_payload.get("folds", [])
    fold_for: dict[int, int] = {}
    folds_ok = len(fold_rows) == 5
    for item in fold_rows:
        fold = int(item["fold"])
        train = [int(x) for x in item["train_indices"]]
        test = [int(x) for x in item["test_indices"]]
        folds_ok = folds_ok and not set(train) & set(test)
        folds_ok = folds_ok and item.get("fold_sha256") == canonical({
            "fold": fold, "train_indices": train, "test_indices": test,
            "test_tuples": item["test_tuples"]})
        for index in test:
            if index in fold_for:
                folds_ok = False
            fold_for[index] = fold
    folds_ok = folds_ok and sorted(fold_for) == list(range(112))
    checks["folds_each_index_once_and_hash_bound"] = bool(folds_ok)

    comparison = json.loads(COMPARISON.read_text())
    crossfit = json.loads(CROSSFIT.read_text())
    contract = json.loads(CONTRACT.read_text())
    checks["source_and_candidate_contract"] = bool(
        comparison.get("dataset_id") == DATASET_ID and comparison.get("forward_solver_sha") == FORWARD_SHA and
        tuple(comparison.get("candidate_set", [])) == PREDICTORS and
        tuple(comparison.get("risk_rule_set", [])) == RULES and
        crossfit.get("dataset_id") == DATASET_ID and crossfit.get("validation_response_accessed") is False and
        contract.get("model_lock_created") is False and contract.get("blind_fem_authorized") is False and
        contract.get("validation_response_accessed") is False
    )
    code_sha = str(comparison.get("surrogate_training_code_sha", ""))
    checks["single_non_placeholder_implementation_sha"] = bool(code_sha and code_sha != "WORKTREE_M4H" and
                                                                crossfit.get("surrogate_training_code_sha") == code_sha and
                                                                contract.get("surrogate_training_code_sha") == code_sha)

    base = json.loads(BASE_OOF.read_text())
    base_rows = base.get("records", {})
    selective = json.loads(OOF.read_text())
    selective_rows = selective.get("records", {})
    oof_ok = selective.get("dataset_id") == DATASET_ID and selective.get("validation_response_accessed") is False
    comparison_ok = True
    for predictor in PREDICTORS:
        for rule in RULES:
            key = f"{predictor}::{rule}"
            rows = selective_rows.get(key, [])
            oof_ok = oof_ok and len(rows) == 112
            if len(rows) != 112:
                continue
            indices = sorted(int(row["sample_index"]) for row in rows)
            oof_ok = oof_ok and indices == list(range(112))
            accepted: list[int] = []
            truth = np.asarray([row["truth"] for row in rows], dtype=float)
            prediction = np.asarray([row["prediction"] for row in rows], dtype=float)
            std = np.asarray([row["std"] for row in rows], dtype=float)
            for row in rows:
                index = int(row["sample_index"])
                fold = int(row["fold"])
                source_folds = [int(x) for x in row["threshold_source_folds"]]
                source_indices = [i for i in range(112) if fold_for[i] in source_folds]
                oof_ok = oof_ok and fold_for.get(index) == fold and fold not in source_folds
                oof_ok = oof_ok and row.get("threshold_source_indices_hash") == canonical(source_indices)
                # Risk arithmetic is rebuilt from the compact scaled components.
                comp = row["risk_components"]
                nstd = np.asarray(comp["native_std_scaled"], dtype=float)
                d12 = np.asarray(comp["rbf_matern_disagreement_scaled"], dtype=float)
                d23 = np.asarray(comp["matern_k24_k32_disagreement_scaled"], dtype=float)
                distance = np.asarray(comp["nearest_training_distance_scaled"], dtype=float)
                geometry = np.asarray(comp["cutoff_topology_scaled"], dtype=float)
                if rule == RULES[0]:
                    risk_target = (WEIGHTS["native_std"] * nstd + WEIGHTS["matern_k24_k32_disagreement"] * d23 +
                                   WEIGHTS["rbf_matern_disagreement"] * d12 +
                                   WEIGHTS["nearest_training_distance"] * distance +
                                   WEIGHTS["cutoff_topology_bonus"] * geometry)
                else:
                    risk_target = np.maximum(np.maximum(nstd, d12), d23)
                risk = float(np.max(risk_target))
                oof_ok = oof_ok and abs(risk - float(row["risk_score"])) <= 1.0e-10
                expected_accept = risk <= float(row["threshold"]) + 1.0e-15
                oof_ok = oof_ok and bool(row["accepted"]) == expected_accept and row.get("response_used_for_acceptance") is False
                oof_ok = oof_ok and close(row["error"], prediction[index] - truth[index], 1.0e-12)
                oof_ok = oof_ok and close(row["absolute_error"], np.abs(prediction[index] - truth[index]), 1.0e-12)
                if expected_accept:
                    accepted.append(index)
            result = comparison.get("results", {}).get(key, {})
            oof_ok = oof_ok and result.get("accepted_indices") == accepted
            oof_ok = oof_ok and result.get("accepted_indices_sha256") == canonical(accepted)
            rejected = [index for index in range(112) if index not in accepted]
            oof_ok = oof_ok and result.get("rejected_indices") == rejected
            oof_ok = oof_ok and result.get("rejected_indices_sha256") == canonical(rejected)
            reported_metrics = result.get("metrics_accepted", {})
            recomputed = metrics_all(truth, prediction, accepted)
            for target in TARGETS:
                for name in ("nrmse", "p95_abs", "max_abs"):
                    oof_ok = oof_ok and abs(float(recomputed[target][name]) - float(reported_metrics[target][name])) <= 1.0e-10
            coverage_values = np.mean(np.abs(prediction[accepted] - truth[accepted]) <=
                                      1.96 * np.maximum(std[accepted], 1.0e-12), axis=0) if accepted else np.zeros(3)
            for i, target in enumerate(TARGETS):
                oof_ok = oof_ok and abs(float(coverage_values[i]) - float(result.get("coverage_accepted", {}).get(target, -9))) <= 1.0e-10
            comparison_ok = comparison_ok and key in comparison.get("results", {})
    checks["crossfit_oof_no_leakage_and_metrics"] = bool(oof_ok)
    checks["all_six_selective_pairs_present"] = bool(comparison_ok and
                                                       set(selective_rows) == {f"{p}::{r}" for p in PREDICTORS for r in RULES})

    acceptance = json.loads(ACCEPTANCE.read_text())
    acceptance_ok = bool(acceptance.get("dataset_id") == DATASET_ID and
                         acceptance.get("response_blind") is True and
                         acceptance.get("validation_response_accessed") is False)
    for design_name, count_key in (("candidate_pool", 4096), ("blind_design", 24)):
        design = acceptance.get(design_name, {})
        for predictor in PREDICTORS:
            for rule in RULES:
                key = f"{predictor}::{rule}"
                item = design.get(key, {})
                risk = np.asarray(item.get("risk_score", []), dtype=float)
                accepted = [int(x) for x in item.get("accepted_indices", [])]
                rejected = [int(x) for x in item.get("rejected_indices", [])]
                acceptance_ok = acceptance_ok and len(risk) == count_key and \
                    len(set(accepted) & set(rejected)) == 0 and \
                    sorted(accepted + rejected) == list(range(count_key))
                expected = np.flatnonzero(risk <= float(item.get("threshold", np.inf)) + 1.0e-15).astype(int).tolist()
                acceptance_ok = acceptance_ok and accepted == expected and item.get("accepted_count") == len(accepted)
                acceptance_ok = acceptance_ok and item.get("accepted_indices_sha256") == canonical(accepted)
                acceptance_ok = acceptance_ok and item.get("rejected_indices_sha256") == canonical(rejected)
                acceptance_ok = acceptance_ok and item.get("response_used_for_acceptance") is False
    checks["response_blind_pool_and_blind_acceptance"] = bool(acceptance_ok)

    structural = json.loads(STRUCTURAL.read_text())
    structural_ok = bool(structural.get("dataset_id") == DATASET_ID and structural.get("response_blind") is True and
                          structural.get("validation_response_accessed") is False)
    for name, count in (("candidate_pool", 4096), ("blind_design", 24)):
        item = structural.get(name, {})
        rows = item.get("rows", [])
        structural_ok = structural_ok and item.get("count") == count and len(rows) == count
        structural_ok = structural_ok and item.get("supported_count") == sum(bool(row.get("structural_supported")) for row in rows)
    checks["structural_support_domain_is_separate"] = bool(structural_ok)

    checks["controlled_negative_and_no_lock"] = bool(
        contract.get("qualified") is False and contract.get("controlled_negative") is True and
        comparison.get("qualified_pair") == [] and
        not (OUTCOMES / "ANGLE_AGGREGATE_SELECTIVE_MODEL_SELECTION_LOCK.json").exists() and
        not (OUTCOMES / "blind24_preacceptance_manifest.json").exists()
    )
    checks["order_remains_unqualified"] = bool(contract.get("aggregate_only") is True and
                                                contract.get("order_resolved_qualified") is False)
    checks["all_checks"] = bool(all(checks.values()) and not errors)
    return write_result(checks, errors)


def write_result(checks: dict[str, bool], errors: list[str]) -> int:
    result = {"schema_version": "case129.check.v1",
              "status": "pass" if checks.get("all_checks", False) else "fail",
              "qualification_status": "controlled_negative",
              "checks": checks, "errors": errors, "dataset_id": DATASET_ID,
              "training_count": 112, "candidate_pool_count": 4096, "blind_design_count": 24,
              "forward_solver_sha": FORWARD_SHA, "validation_response_accessed": False,
              "new_fem_budget": 0, "model_lock_created": False, "blind_fem_run": False}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
