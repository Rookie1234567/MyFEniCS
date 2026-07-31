"""Training-only deterministic first active-learning plan for Task003 M3S."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .dataset import CASE119_ROOT, load_training_dataset
from .features import FROZEN_FEATURE_CANDIDATE, transform_feature_candidate


ROOT = Path("surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training")
OUT = ROOT / "outcomes"
CASE = Path("benchmarks/cases/121_task003_active_learning_round1")
CANDIDATE = Path("benchmarks/cases/116_task002_single_fidelity_design/candidate_pool.json")
BASELINE_SHA = "10e3356ba8364286a452077f71d7e3b92ea24cd5"
POOL_SHA = "a9831ffc1055732660bee859382f623e8558560634d9ac98702cfe355ff09fcd"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def _points(path: Path) -> tuple[dict[str, Any], np.ndarray]:
    design = json.loads(path.read_text())
    values = np.asarray([[float(row[k]) for k in
                          ("height_nm", "width_x_nm", "grazing_deg", "azimuth_deg")]
                         for row in design["points"]], dtype=np.float64)
    return design, values


def _nearest(values: np.ndarray, reference: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    distances = np.linalg.norm(values[:, None, :] - reference[None, :, :], axis=2)
    index = np.argmin(distances, axis=1)
    return index, distances[np.arange(len(values)), index]


def _cutoff_score(values: np.ndarray) -> np.ndarray:
    grazing = np.deg2rad(values[:, 2]); azimuth = np.deg2rad(values[:, 3])
    kx = np.cos(grazing) * np.cos(azimuth); ky = np.cos(grazing) * np.sin(azimuth)
    margins = np.stack([np.abs(1.0 - ((kx + m * 13.5 / 50.0) ** 2 + ky ** 2))
                        for m in range(-7, 4)], axis=1)
    return 1.0 / (1.0 + 100.0 * np.min(margins, axis=1))


def _region_labels(values: np.ndarray) -> list[list[str]]:
    cutoff = _cutoff_score(values)
    result: list[list[str]] = []
    for row, cut in zip(values, cutoff):
        labels: list[str] = []
        if row[2] <= 2.0: labels.append("low_grazing")
        if row[3] >= 75.0: labels.append("high_azimuth")
        # ``cut`` is deliberately stricter than the ranking score: only the
        # narrow Rayleigh neighborhood is labelled cutoff, leaving an honest
        # interior regime for maximin coverage.
        if cut >= 0.85: labels.append("cutoff")
        if row[0] in (115.0, 125.0) or row[1] in (16.0, 18.0): labels.append("geometry_extreme")
        if not labels: labels.append("interior")
        result.append(labels)
    return result


def _normalise(values: np.ndarray) -> np.ndarray:
    value = np.asarray(values, dtype=np.float64)
    span = float(np.ptp(value))
    return (value - np.min(value)) / (span if span > 0 else 1.0)


def build_plan() -> dict[str, Any]:
    contract = json.loads((OUT / "FEATURE_CONTRACT_v2.json").read_text())
    if contract.get("frozen_candidate") != FROZEN_FEATURE_CANDIDATE:
        raise RuntimeError("feature-B contract is not frozen")
    dataset = load_training_dataset(CASE119_ROOT)
    design, pool = _points(CANDIDATE)
    if design.get("point_tuple_sha256") != POOL_SHA:
        raise RuntimeError("candidate pool tuple hash changed")
    # Input-side exclusions only; no frozen-validation target file is opened.
    excluded = [dataset.inputs]
    for path in (
        Path("benchmarks/cases/116_task002_single_fidelity_design/frozen_validation_design.json"),
        Path("benchmarks/cases/116_task002_single_fidelity_design/discretization_audit_design.json"),
    ):
        excluded.append(_points(path)[1])
    excluded_points = np.vstack(excluded)
    dist_excluded = np.min(np.linalg.norm(pool[:, None, :] - excluded_points[None, :, :], axis=2), axis=1)
    allowed = dist_excluded > 1.0e-8
    x_train = transform_feature_candidate(dataset.inputs, "B")
    x_pool = transform_feature_candidate(pool, "B")
    nearest, nearest_distance = _nearest(x_pool, x_train)
    cv = json.loads((OUT / "training_cv.json").read_text())
    records = json.loads((OUT / "training_cv_oof.json").read_text())["records"]
    agg_abs = np.zeros(dataset.n_samples); agg_std = np.zeros(dataset.n_samples)
    agg_count = np.zeros(dataset.n_samples)
    p2_abs = np.zeros(dataset.n_samples); p2_count = np.zeros(dataset.n_samples)
    for row in records:
        i = int(row["sample_index"])
        if row.get("target_type") == "aggregate":
            agg_abs[i] += abs(float(row["error"]))
            agg_std[i] += abs(float(row["std"]))
            agg_count[i] += 1
        elif row.get("target_type") == "order_power_p2" and row.get("error") is not None:
            p2_abs[i] += abs(float(row["error"]))
            p2_count[i] += 1
    agg_abs /= np.maximum(agg_count, 1); agg_std /= np.maximum(agg_count, 1)
    p2_abs /= np.maximum(p2_count, 1)
    factor = float(cv["uncertainty_diagnostics"]["multiplicative_training_oof_calibration_factor"])
    uncertainty = factor * agg_std[nearest]
    error_surrogate = agg_abs[nearest]
    primary_power = p2_abs[nearest]
    distance = nearest_distance
    cutoff = _cutoff_score(pool)
    score = (0.30 * _normalise(uncertainty) + 0.25 * _normalise(error_surrogate)
             + 0.10 * _normalise(distance) + 0.20 * _normalise(cutoff)
             + 0.15 * _normalise(primary_power))
    score[~allowed] = -np.inf
    labels = _region_labels(pool)
    selected: list[int] = []
    # Guarantee coverage of the four prescribed acquisition regimes whenever
    # the candidate pool contains an admissible point in that regime.
    for regime in ("low_grazing", "cutoff", "high_azimuth", "interior"):
        candidates = [i for i in np.flatnonzero(allowed) if regime in labels[i] and i not in selected]
        if candidates:
            selected.append(max(candidates, key=lambda i: float(score[i])))
    while len(selected) < 8:
        remaining = [i for i in np.flatnonzero(allowed) if i not in selected]
        if not remaining: break
        def utility(i: int) -> float:
            diversity = min(float(np.linalg.norm(x_pool[i] - x_pool[j])) for j in selected)
            return float(score[i] + 0.08 * diversity)
        selected.append(max(remaining, key=utility))
    selected = sorted(selected, key=lambda i: (-float(score[i]), int(i)))[:8]
    planned = []
    for i in selected:
        planned.append({
            "candidate_index": int(i),
            "point": [float(v) for v in pool[i]],
            "role": "active_learning_round1",
            "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
            "source_sha": BASELINE_SHA, "source_dirty": False,
            "region_labels": labels[i], "acquisition_score": float(score[i]),
            "score_components": {
                "aggregate_calibrated_uncertainty": float(uncertainty[i]),
                "oof_abs_error_surrogate": float(error_surrogate[i]),
                "feature_B_nearest_distance": float(distance[i]),
                "cutoff_proximity": float(cutoff[i]),
                "primary_power_error_contribution": float(primary_power[i]),
            },
        })
    return {
        "schema_version": "task003.active-learning-round1-plan.v1",
        "status": "checker_pending",
        "training_dataset_id": dataset.dataset_id, "training_count": 96,
        "candidate_pool_sha256": POOL_SHA, "candidate_pool_count": 4096,
        "excluded_existing_training_validation_audit": True,
        "frozen_validation_target_accessed": False,
        "feature_contract": {"path": str(OUT / "FEATURE_CONTRACT_v2.json"),
                              "candidate": FROZEN_FEATURE_CANDIDATE,
                              "sha256": hashlib.sha256((OUT / "FEATURE_CONTRACT_v2.json").read_bytes()).hexdigest()},
        "baseline_sha": BASELINE_SHA, "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
        "mesh": {"axis_cell_counts": [6, 4, 14], "degree": 5, "h_nm": 10.0,
                 "mpi_ranks": 2, "threads_per_rank": 1},
        "acquisition_formula": "0.30 calibrated aggregate uncertainty + 0.25 OOF abs-error surrogate + 0.10 feature-B distance + 0.20 cutoff proximity + 0.15 primary-power contribution",
        "selection": {"maximin_diversity": True, "required_regimes": ["low_grazing", "cutoff", "high_azimuth", "interior"]},
        "points": planned,
        "point_tuple_sha256": _hash([row["point"] for row in planned]),
        "round": 1, "budget": 8, "next_round_authorized": False,
    }


def main() -> int:
    plan = build_plan()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ACTIVE_LEARNING_ROUND1_PLAN.json").write_text(json.dumps(plan, indent=2) + "\n")
    CASE.mkdir(parents=True, exist_ok=True)
    (CASE / "config.json").write_text(json.dumps(plan, indent=2) + "\n")
    print(json.dumps({"status": "plan_written", "points": len(plan["points"]),
                      "tuple_hash": plan["point_tuple_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
