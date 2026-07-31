"""Deterministic, diversity-constrained Round-2 plan after M3T authorization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .active_learning import _cutoff_score, _normalise, _points
from .dataset import load_training_dataset
from .features import transform_feature_candidate


OUT = Path("surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/outcomes")
CASE = Path("benchmarks/cases/122_task003_round1_fixed_reference_and_optional_round2")
POOL_PATH = Path("benchmarks/cases/116_task002_single_fidelity_design/candidate_pool.json")
DATA = Path("benchmarks/artifacts/cases/121_task003_active_learning_round1_retry_cachefix/compact_dataset")
BASELINE = "10e3356ba8364286a452077f71d7e3b92ea24cd5"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _labels(points: np.ndarray) -> list[dict[str, Any]]:
    cutoff = _cutoff_score(points)
    result = []
    for row, cut in zip(points, cutoff):
        low = bool(row[2] <= 2.0)
        high_grazing = bool(row[2] >= 4.0)
        high_azimuth = bool(row[3] >= 60.0)
        interior = bool(not low and not high_azimuth and cut < 0.85)
        h_bin = int(min(2, max(0, np.floor((row[0] - 115.0) / (10.0 / 3.0)))))
        w_bin = int(min(2, max(0, np.floor((row[1] - 16.0) / (2.0 / 3.0)))))
        signature = f"{'low' if low else 'nonlow'}|{'highaz' if high_azimuth else 'az0_60'}|{'cutoff' if cut >= 0.85 else 'interior'}|h{h_bin}w{w_bin}"
        result.append({"low_grazing": low, "high_grazing": high_grazing,
                       "high_azimuth": high_azimuth, "ordinary_interior": interior,
                       "cutoff": bool(cut >= 0.85), "h_bin": h_bin, "w_bin": w_bin,
                       "signature": signature})
    return result


def _normal(value: np.ndarray) -> np.ndarray:
    return _normalise(value)


def build_plan() -> dict[str, Any]:
    status = json.loads((OUT / "ROUND1_COMPLETION_STATUS.json").read_text())
    if not status.get("round2_authorized"):
        raise RuntimeError("M3T Gate did not authorize Round 2")
    pool_design, pool = _points(POOL_PATH)
    dataset = load_training_dataset(DATA)
    validation = _points(Path("benchmarks/cases/116_task002_single_fidelity_design/frozen_validation_design.json"))[1]
    audit = _points(Path("benchmarks/cases/116_task002_single_fidelity_design/discretization_audit_design.json"))[1]
    blocked = np.vstack((dataset.inputs, validation, audit))
    distance_blocked = np.min(np.linalg.norm(pool[:, None, :] - blocked[None, :, :], axis=2), axis=1)
    allowed = distance_blocked > 1.0e-8
    x_train = transform_feature_candidate(dataset.inputs, "B")
    x_pool = transform_feature_candidate(pool, "B")
    distances = np.linalg.norm(x_pool[:, None, :] - x_train[None, :, :], axis=2)
    nearest = np.argmin(distances, axis=1)
    nearest_distance = distances[np.arange(len(pool)), nearest]
    cv = json.loads((OUT / "training_cv_104.json").read_text())
    records = json.loads((OUT / "training_cv_104_oof.json").read_text())["records"]
    agg_error = np.zeros(104); agg_std = np.zeros(104); agg_count = np.zeros(104)
    p2_error = np.zeros(104); p2_count = np.zeros(104)
    for row in records:
        i = int(row["sample_index"])
        if row.get("target_type") == "aggregate":
            agg_error[i] += abs(float(row["error"])); agg_std[i] += abs(float(row["std"])); agg_count[i] += 1
        elif row.get("target_type") == "order_power_p2" and row.get("error") is not None:
            p2_error[i] += abs(float(row["error"])); p2_count[i] += 1
    agg_error /= np.maximum(agg_count, 1); agg_std /= np.maximum(agg_count, 1); p2_error /= np.maximum(p2_count, 1)
    cutoff = _cutoff_score(pool)
    score = (0.35 * _normal(agg_error[nearest]) + 0.25 * _normal(agg_std[nearest])
             + 0.15 * _normal(nearest_distance) + 0.15 * _normal(cutoff)
             + 0.10 * _normal(p2_error[nearest]))
    score[~allowed] = -np.inf
    labels = _labels(pool)
    selected: list[int] = []

    def add_best(predicate):
        candidates = [i for i in np.flatnonzero(allowed) if i not in selected and predicate(i)]
        if candidates:
            # Score plus a small feature-space diversity term.
            def utility(i):
                diversity = min((np.linalg.norm(x_pool[i] - x_pool[j]) for j in selected), default=1.0)
                return float(score[i] + 0.06 * diversity)
            selected.append(max(candidates, key=utility))

    # Explicitly satisfy the review's domain-wide quotas first.
    add_best(lambda i: labels[i]["high_grazing"] and labels[i]["high_azimuth"])
    add_best(lambda i: labels[i]["high_grazing"] and not labels[i]["high_azimuth"])
    add_best(lambda i: labels[i]["high_azimuth"] and not labels[i]["high_grazing"])
    add_best(lambda i: labels[i]["ordinary_interior"] and labels[i]["h_bin"] == 0)
    add_best(lambda i: labels[i]["ordinary_interior"] and labels[i]["h_bin"] == 2)
    add_best(lambda i: labels[i]["ordinary_interior"] and labels[i]["w_bin"] == 0)
    while len(selected) < 8:
        candidates = [i for i in np.flatnonzero(allowed) if i not in selected]
        if not candidates:
            break
        def utility(i):
            diversity = min((np.linalg.norm(x_pool[i] - x_pool[j]) for j in selected), default=1.0)
            low_penalty = 0.25 if labels[i]["low_grazing"] and sum(labels[j]["low_grazing"] for j in selected) >= 3 else 0.0
            signature_bonus = 0.10 if labels[i]["signature"] not in {labels[j]["signature"] for j in selected} else 0.0
            return float(score[i] + 0.06 * diversity + signature_bonus - low_penalty)
        selected.append(max(candidates, key=utility))
    # A deterministic repair loop enforces all quotas if greedy ties leave one
    # short; it never relaxes the maximum-low-grazing rule.
    for _ in range(32):
        flags = _labels(pool[selected])
        if (sum(x["low_grazing"] for x in flags) <= 3 and sum(x["high_grazing"] for x in flags) >= 2
                and sum(x["high_azimuth"] for x in flags) >= 2 and sum(x["ordinary_interior"] for x in flags) >= 2
                and len({x["signature"] for x in flags}) >= 4 and len({x["h_bin"] for x in flags}) >= 3
                and len({x["w_bin"] for x in flags}) >= 3):
            break
        # Replace the lowest-scoring point that does not itself satisfy a
        # currently missing constraint.
        missing = []
        if sum(x["high_grazing"] for x in flags) < 2: missing.append(lambda x: x["high_grazing"])
        if sum(x["high_azimuth"] for x in flags) < 2: missing.append(lambda x: x["high_azimuth"])
        if sum(x["ordinary_interior"] for x in flags) < 2: missing.append(lambda x: x["ordinary_interior"])
        if len({x["h_bin"] for x in flags}) < 3: missing.append(lambda x: x["h_bin"] not in {q["h_bin"] for q in flags})
        if len({x["w_bin"] for x in flags}) < 3: missing.append(lambda x: x["w_bin"] not in {q["w_bin"] for q in flags})
        replacement = None
        for predicate in missing:
            candidates = [i for i in np.flatnonzero(allowed) if i not in selected and predicate(labels[i]) and not labels[i]["low_grazing"]]
            if candidates:
                replacement = max(candidates, key=lambda i: float(score[i])); break
        if replacement is None: break
        victim = min(range(len(selected)), key=lambda pos: float(score[selected[pos]]))
        selected[victim] = replacement
    selected = sorted(selected, key=lambda i: (-float(score[i]), int(i)))[:8]
    flags = _labels(pool[selected])
    if not (sum(x["low_grazing"] for x in flags) <= 3 and sum(x["high_grazing"] for x in flags) >= 2
            and sum(x["high_azimuth"] for x in flags) >= 2 and sum(x["ordinary_interior"] for x in flags) >= 2
            and len({x["signature"] for x in flags}) >= 4 and len({x["h_bin"] for x in flags}) >= 3
            and len({x["w_bin"] for x in flags}) >= 3):
        raise RuntimeError("unable to satisfy Round2 diversity constraints")
    points = []
    for i, lab in zip(selected, flags):
        points.append({"candidate_index": int(i), "point": pool[i].tolist(),
                       "role": "active_learning_round2", "model_id": MODEL_ID,
                       "solver_route_id": ROUTE_ID, "source_sha": BASELINE,
                       "source_dirty": False, "region_signature": lab["signature"],
                       "region_labels": lab, "acquisition_score": float(score[i]),
                       "score_components": {"aggregate_error_surrogate": float(agg_error[nearest[i]]),
                                            "aggregate_uncertainty_surrogate": float(agg_std[nearest[i]]),
                                            "feature_B_nearest_distance": float(nearest_distance[i]),
                                            "cutoff_proximity": float(cutoff[i]),
                                            "primary_power_error_contribution": float(p2_error[nearest[i]])}})
    return {"schema_version": "task003.active-learning-round2-plan.v1", "status": "checker_pending",
            "round": 2, "budget": 8, "training_count_before": 104,
            "candidate_pool_sha256": pool_design["point_tuple_sha256"], "candidate_pool_count": 4096,
            "feature_candidate": "B", "validation_target_accessed": False,
            "baseline_sha": BASELINE, "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
            "mesh": {"axis_cell_counts": [6, 4, 14], "degree": 5, "h_nm": 10.0, "mpi_ranks": 2, "threads_per_rank": 1},
            "diversity_constraints": {"max_low_grazing": 3, "min_grazing_ge_4": 2,
                                      "min_azimuth_ge_60": 2, "min_ordinary_interior": 2,
                                      "min_h_bins": 3, "min_w_bins": 3, "min_region_signatures": 4},
            "acquisition_formula": "104-row OOF aggregate error/uncertainty + feature-B distance + cutoff + P2 contribution with maximin diversity",
            "points": points, "point_tuple_sha256": _hash([row["point"] for row in points]),
            "round3_authorized": False}


def main() -> int:
    plan = build_plan(); CASE.mkdir(parents=True, exist_ok=True)
    (OUT / "ACTIVE_LEARNING_ROUND2_PLAN.json").write_text(json.dumps(plan, indent=2) + "\n")
    (CASE / "config.json").write_text(json.dumps(plan, indent=2) + "\n")
    design = {"schema_version": "task002.m3r-design.v1",
              "design_id": "task003_active_learning_round2_training",
              "source_sha": BASELINE, "source_dirty": False,
              "parameter_schema_version": "task002.s-p5-ny4-production-parameters.v3",
              "observable_schema_version": "task002.fixed-n0-orders.v3",
              "production_model_id": MODEL_ID, "production_solver_route_id": ROUTE_ID,
              "point_count": 8, "point_tuple_sha256": plan["point_tuple_sha256"], "points": []}
    for row in plan["points"]:
        point = row["point"]
        design["points"].append({"height_nm": point[0], "width_x_nm": point[1],
                                  "grazing_deg": point[2], "azimuth_deg": point[3],
                                  "role": "active_learning_round2",
                                  "design_source": f"candidate_pool_index_{row['candidate_index']}",
                                  "model_id": MODEL_ID, "solver_route_id": ROUTE_ID})
    (CASE / "round2_design.json").write_text(json.dumps(design, indent=2) + "\n")
    print(json.dumps({"status": "plan_written", "points": len(plan["points"]),
                      "tuple_hash": plan["point_tuple_sha256"]}, indent=2))
    for row in plan["points"]:
        print(row["candidate_index"], row["point"], row["region_signature"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
