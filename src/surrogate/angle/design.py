"""Deterministic Task004 angle designs.

The design generator is response-blind: it uses only analytic wave-vector
geometry and distances in the two-dimensional angle domain.  No FEM output or
Task003 validation target is opened.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import qmc


MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
PARAMETER_SCHEMA = "task002.s-p5-ny4-production-parameters.v3"
OBSERVABLE_SCHEMA = "task002.fixed-n0-orders.v3"
DESIGN_SCHEMA = "task002.m3r-design.v1"
HEIGHT = 120.0
WIDTH = 17.0
GRAZING_RANGE = (0.5, 10.0)
AZIMUTH_RANGE = (0.0, 90.0)
STRUCTURED_GRAZING = (0.5, 0.75, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0)
STRUCTURED_AZIMUTH = (0.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 75.0, 90.0)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def point_tuple(point: dict[str, Any]) -> list[float]:
    return [float(point[key]) for key in ("height_nm", "width_x_nm", "grazing_deg", "azimuth_deg")]


def cutoff_margins(angles: np.ndarray) -> np.ndarray:
    """Signed dispersion margins for n=0 orders m=-7..+3."""

    values = np.asarray(angles, dtype=np.float64)
    grazing = np.deg2rad(values[:, 0]); azimuth = np.deg2rad(values[:, 1])
    kx = np.cos(grazing) * np.cos(azimuth)
    ky = np.cos(grazing) * np.sin(azimuth)
    shift = 13.5 / 50.0
    return np.stack([1.0 - ((kx + m * shift) ** 2 + ky ** 2)
                     for m in range(-7, 4)], axis=1)


def cutoff_distance(angles: np.ndarray) -> np.ndarray:
    return np.min(np.abs(cutoff_margins(angles)), axis=1)


def _sobol_angles(seed: int, count: int) -> np.ndarray:
    engine = qmc.Sobol(d=2, scramble=True, seed=seed)
    unit = engine.random(count)
    return np.column_stack((GRAZING_RANGE[0] + np.ptp(GRAZING_RANGE) * unit[:, 0],
                            AZIMUTH_RANGE[0] + np.ptp(AZIMUTH_RANGE) * unit[:, 1]))


def _normal_angle_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    scale = np.asarray([np.ptp(GRAZING_RANGE), np.ptp(AZIMUTH_RANGE)])
    return np.linalg.norm((a[:, None, :] - b[None, :, :]) / scale, axis=2)


def _labels(angles: np.ndarray) -> list[dict[str, Any]]:
    margins = cutoff_distance(angles)
    result = []
    for point, distance in zip(angles, margins):
        low = bool(point[0] <= 2.0)
        high_azimuth = bool(point[1] >= 75.0)
        cutoff = bool(distance <= 0.02)
        interior = bool(not low and not high_azimuth and not cutoff)
        result.append({
            "low_grazing": low, "high_azimuth": high_azimuth,
            "cutoff_near": cutoff, "ordinary_interior": interior,
            "cutoff_distance": float(distance),
            "region": ("low_grazing" if low else "high_azimuth" if high_azimuth
                       else "cutoff_near" if cutoff else "ordinary_interior"),
        })
    return result


def _select_enrichment(pool: np.ndarray, structured: np.ndarray) -> np.ndarray:
    labels = _labels(pool)
    selected: list[int] = []

    def choose(predicate):
        candidates = [i for i, label in enumerate(labels)
                      if predicate(label) and i not in selected]
        if not candidates:
            raise RuntimeError("Task004 candidate pool lacks required enrichment regime")
        # Prefer a point far from the structured grid and already selected points.
        def score(index: int) -> float:
            from_grid = float(np.min(_normal_angle_distance(pool[index:index + 1], structured)))
            from_selected = (float(np.min(_normal_angle_distance(
                pool[index:index + 1], pool[np.asarray(selected)])))
                             if selected else 1.0)
            return 0.55 * from_grid + 0.45 * from_selected
        selected.append(max(candidates, key=score))

    # Four prescribed regimes first; low/cutoff overlap is intentional.
    for predicate in (
        lambda x: x["low_grazing"], lambda x: x["cutoff_near"],
        lambda x: x["high_azimuth"], lambda x: x["ordinary_interior"],
    ):
        choose(predicate)
    while len(selected) < 16:
        candidates = [i for i in range(len(pool)) if i not in selected]
        selected.append(max(candidates, key=lambda i: min(
            float(np.min(_normal_angle_distance(pool[i:i + 1], pool[np.asarray(selected)]))),
            float(np.min(_normal_angle_distance(pool[i:i + 1], structured))),
        )))
    return pool[np.asarray(selected)]


def _validation_angles(training: np.ndarray) -> np.ndarray:
    all_domain = _sobol_angles(seed=20260803, count=16)
    low_pool = _sobol_angles(seed=20260805, count=256)
    low = low_pool[np.argsort(low_pool[:, 0])[:4]]
    cutoff_pool = _sobol_angles(seed=20260806, count=512)
    cutoff = cutoff_pool[np.argsort(cutoff_distance(cutoff_pool))[:4]]
    values = np.vstack((all_domain, low, cutoff))
    # Deterministically repair the extremely unlikely exact collision with a
    # training point without consulting any response.
    for index in range(len(values)):
        while np.any(np.linalg.norm(training - values[index], axis=1) < 1.0e-10):
            values[index, 1] = (values[index, 1] + 0.137) % 90.0
    if len({tuple(row) for row in values}) != 24:
        raise RuntimeError("Task004 blind validation angles are not unique")
    return values


def _point(angle: np.ndarray, *, role: str, source: str) -> dict[str, Any]:
    return {"height_nm": HEIGHT, "width_x_nm": float(WIDTH),
            "grazing_deg": float(angle[0]), "azimuth_deg": float(angle[1]),
            "role": role, "design_source": source,
            "model_id": MODEL_ID, "solver_route_id": ROUTE_ID}


def _design(design_id: str, points: list[dict[str, Any]], *, source_sha: str,
            sobol_seed: int | None = None) -> dict[str, Any]:
    tuples = [point_tuple(row) for row in points]
    return {
        "schema_version": DESIGN_SCHEMA, "design_id": design_id,
        "source_sha": source_sha, "source_dirty": False,
        "parameter_schema_version": PARAMETER_SCHEMA,
        "observable_schema_version": OBSERVABLE_SCHEMA,
        "production_model_id": MODEL_ID,
        "production_solver_route_id": ROUTE_ID,
        "sobol_seed": sobol_seed, "point_count": len(points),
        "point_tuple_sha256": canonical_hash(tuples), "points": points,
    }


def build_designs(*, source_sha: str) -> dict[str, dict[str, Any]]:
    structured = np.asarray([[g, a] for g in STRUCTURED_GRAZING
                             for a in STRUCTURED_AZIMUTH], dtype=np.float64)
    pool = _sobol_angles(seed=20260802, count=4096)
    enrichment = _select_enrichment(pool, structured)
    training = np.vstack((structured, enrichment))
    validation = _validation_angles(training)
    anchors = np.asarray([[0.5, 0.0], [0.5, 90.0], [10.0, 0.0],
                          [10.0, 90.0], [5.25, 45.0]], dtype=np.float64)
    if any(np.any(np.linalg.norm(training - row, axis=1) < 1.0e-10) for row in anchors):
        pass
    designs = {
        "training": _design(
            "task004_angle_training_v1",
            [_point(row, role="structured_angle" if i < 80 else "cutoff_low_grazing_enrichment",
                    source="task004_structured_80" if i < 80 else "task004_sobol_4096_enrichment")
             for i, row in enumerate(training)], source_sha=source_sha, sobol_seed=20260802),
        "validation": _design(
            "task004_angle_frozen_validation_v1",
            [_point(row, role="blind_validation",
                    source="task004_sobol_all_domain_16" if i < 16
                    else "task004_low_grazing_4" if i < 20 else "task004_cutoff_near_4")
             for i, row in enumerate(validation)], source_sha=source_sha, sobol_seed=20260803),
        "candidate_pool": _design(
            "task004_angle_candidate_pool_v1",
            [_point(row, role="candidate_pool", source="task004_sobol_4096") for row in pool],
            source_sha=source_sha, sobol_seed=20260802),
        "anchors": _design(
            "task004_anchor_training_v1",
            [_point(row, role="clean_sha_anchor", source="case119_center_geometry_training_anchor") for row in anchors],
            source_sha=source_sha),
    }
    return designs


def write_designs(output_dir: Path, *, source_sha: str) -> dict[str, dict[str, Any]]:
    designs = build_designs(source_sha=source_sha)
    output_dir.mkdir(parents=True, exist_ok=True)
    names = {"training": "training_design.json", "validation": "frozen_validation_design.json",
             "candidate_pool": "candidate_pool.json", "anchors": "anchor_design.json"}
    for key, design in designs.items():
        (output_dir / names[key]).write_text(json.dumps(design, indent=2) + "\n")
    split = {
        "schema_version": "task004.angle-design-splits.v1", "source_sha": source_sha,
        "training_sha256": designs["training"]["point_tuple_sha256"],
        "validation_sha256": designs["validation"]["point_tuple_sha256"],
        "candidate_pool_sha256": designs["candidate_pool"]["point_tuple_sha256"],
        "anchor_sha256": designs["anchors"]["point_tuple_sha256"],
        "training_validation_intersection": sorted(set(
            map(tuple, [point_tuple(p) for p in designs["training"]["points"]])) & set(
            map(tuple, [point_tuple(p) for p in designs["validation"]["points"]]))),
    }
    split["combined_design_sha256"] = canonical_hash({k: split[k] for k in (
        "training_sha256", "validation_sha256", "candidate_pool_sha256", "anchor_sha256")})
    (output_dir / "split_hashes.json").write_text(json.dumps(split, indent=2) + "\n")
    return designs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    designs = write_designs(args.output_dir, source_sha=args.source_sha)
    print(json.dumps({key: {"count": value["point_count"], "tuple_sha256": value["point_tuple_sha256"]}
                      for key, value in designs.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
