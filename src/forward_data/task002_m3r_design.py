"""Deterministic, hash-bound p5-only Task002 M3R design freezing."""

from __future__ import annotations

import itertools
from typing import Any, Iterable

import numpy as np
from scipy.stats import qmc

from .provenance import canonical_hash
from .task002_schema import (
    TASK002_OBSERVABLE_SCHEMA_VERSION, TASK002_PARAMETER_SCHEMA_VERSION,
)


PRODUCTION_MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10"
PRODUCTION_ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10"
TRAINING_SEED = 20260729
VALIDATION_SEED = 20260730
CANDIDATE_SEED = 20260731
DOMAIN = np.asarray([[115.0, 125.0], [16.0, 18.0], [0.5, 10.0], [0.0, 90.0]])


def _tuple(values: Iterable[float]) -> tuple[float, float, float, float]:
    return tuple(float(value) for value in np.round(np.asarray(tuple(values)), 12))


def _point(values: Iterable[float], *, role: str, source: str) -> dict[str, Any]:
    h, w, grazing, azimuth = _tuple(values)
    return {
        "height_nm": h, "width_x_nm": w, "grazing_deg": grazing,
        "azimuth_deg": azimuth, "role": role, "design_source": source,
        "model_id": PRODUCTION_MODEL_ID, "solver_route_id": PRODUCTION_ROUTE_ID,
    }


def point_tuple(point: dict[str, Any]) -> tuple[float, float, float, float]:
    return _tuple((point["height_nm"], point["width_x_nm"],
                   point["grazing_deg"], point["azimuth_deg"]))


def _scale(unit: np.ndarray) -> np.ndarray:
    return DOMAIN[:, 0] + unit * (DOMAIN[:, 1] - DOMAIN[:, 0])


def _deduplicate(points: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = {}
    for point in points:
        result.setdefault(point_tuple(point), point)
    return list(result.values())


def _metadata(*, source_sha: str, design_id: str, points: list[dict[str, Any]],
              seed: int | None) -> dict[str, Any]:
    tuples = [list(point_tuple(point)) for point in points]
    return {
        "schema_version": "task002.m3r-design.v1", "design_id": design_id,
        "source_sha": source_sha, "source_dirty": False,
        "parameter_schema_version": TASK002_PARAMETER_SCHEMA_VERSION,
        "observable_schema_version": TASK002_OBSERVABLE_SCHEMA_VERSION,
        "production_model_id": PRODUCTION_MODEL_ID,
        "production_solver_route_id": PRODUCTION_ROUTE_ID,
        "sobol_seed": seed, "point_count": len(points),
        "point_tuple_sha256": canonical_hash(tuples), "points": points,
    }


def training_design(source_sha: str) -> dict[str, Any]:
    sobol = qmc.Sobol(d=4, scramble=True, seed=TRAINING_SEED).random_base2(6)
    points = [_point(row, role="sobol_interior", source="scrambled_sobol_64")
              for row in _scale(sobol)]
    corners = itertools.product(*[(lo, hi) for lo, hi in DOMAIN])
    points.extend(_point(row, role="domain_corner", source="deterministic_16_corners")
                  for row in corners)
    angle_anchors = (
        (0.5, 0.0), (0.5, 90.0), (10.0, 0.0), (10.0, 90.0),
        (0.5, 45.0), (10.0, 45.0), (5.25, 0.0), (5.25, 90.0),
        (5.25, 45.0),
    )
    points.extend(_point((120.0, 17.0, g, a), role="center_geometry_angle_anchor",
                         source="deterministic_center_angle_anchors")
                  for g, a in angle_anchors)
    points.extend(_point(row, role="geometry_axis_anchor",
                         source="deterministic_geometry_axes") for row in (
        (117.5, 17.0, 2.0, 15.0), (122.5, 17.0, 2.0, 15.0),
        (120.0, 16.5, 10.0, 45.0), (120.0, 17.5, 10.0, 45.0),
    ))
    # Deterministic near-Rayleigh anchors selected by the v3 dense analytic audit.
    points.extend(_point(row, role="observable_v3_cutoff_anchor",
                         source="dense_n0_rayleigh_audit") for row in (
        (120.0, 17.0, 0.5, 60.0), (120.0, 17.0, 1.0, 75.0),
        (120.0, 17.0, 4.0, 90.0),
    ))
    points = _deduplicate(points)
    return _metadata(source_sha=source_sha, design_id="task002_p5_initial_training_v1",
                     points=points, seed=TRAINING_SEED)


def validation_design(source_sha: str, training: dict[str, Any]) -> dict[str, Any]:
    sobol = qmc.Sobol(d=4, scramble=True, seed=VALIDATION_SEED).random_base2(4)
    points = [_point(row, role="frozen_validation",
                     source="independent_scrambled_sobol_16") for row in _scale(sobol)]
    train = {point_tuple(point) for point in training["points"]}
    overlap = train & {point_tuple(point) for point in points}
    if overlap:
        raise RuntimeError(f"frozen validation intersects training: {sorted(overlap)}")
    result = _metadata(source_sha=source_sha,
                       design_id="task002_p5_frozen_validation_v1",
                       points=points, seed=VALIDATION_SEED)
    result["usage_contract"] = (
        "never used for feature map, transform, kernel, hyperparameter, model, "
        "or acquisition selection; invalidate only for a dataset/source bug"
    )
    result["training_intersection"] = []
    return result


def candidate_pool(source_sha: str, training: dict[str, Any],
                   validation: dict[str, Any]) -> dict[str, Any]:
    # Generate excess deterministic Sobol candidates so exact exclusions never
    # reduce the frozen pool below 4096.
    sobol = qmc.Sobol(d=4, scramble=True, seed=CANDIDATE_SEED).random_base2(13)
    excluded = ({point_tuple(point) for point in training["points"]}
                | {point_tuple(point) for point in validation["points"]})
    points = []
    for row in _scale(sobol):
        point = _point(row, role="candidate_pool", source="scrambled_sobol_candidate")
        if point_tuple(point) not in excluded:
            points.append(point)
        if len(points) == 4096:
            break
    if len(points) != 4096:
        raise RuntimeError("candidate pool cannot retain 4096 disjoint points")
    result = _metadata(source_sha=source_sha, design_id="task002_p5_candidate_pool_v1",
                       points=points, seed=CANDIDATE_SEED)
    result["acquisition_roles"] = [
        "single_gp_uncertainty", "pce_gp_disagreement", "coverage",
        "cutoff_proximity", "fisher_potential",
    ]
    result["excluded_training_validation_intersection"] = []
    return result


def discretization_audit_design(source_sha: str) -> dict[str, Any]:
    points = [_point(row, role="discretization_audit_only", source=source)
              for row, source in (
        ((115.0, 16.0, 0.5, 90.0), "geometry_corner_low_grazing_R_max_region"),
        ((125.0, 18.0, 8.0, 30.0), "geometry_corner_p5_R_min_region"),
        ((115.0, 18.0, 2.0, 45.0), "geometry_corner_absorption_max_region"),
        ((125.0, 16.0, 10.0, 90.0), "geometry_corner_transmission_max_region"),
        ((117.5, 17.0, 0.5, 45.0), "height_axis_low_grazing_conical"),
        ((122.5, 17.0, 2.0, 15.0), "height_axis_intermediate_azimuth"),
        ((120.0, 16.5, 6.0, 60.0), "width_axis_conical"),
        ((120.0, 17.5, 10.0, 45.0), "width_axis_high_grazing"),
    )]
    result = _metadata(source_sha=source_sha,
                       design_id="task002_discretization_audit_candidates_v1",
                       points=points, seed=None)
    result["solver_pair"] = [
        "S_PROD_FULL3D_STATIC_P5_H10",
        "P4_H7P5_DISCRETIZATION_AUDIT",
    ]
    result["production_dataset_membership"] = False
    result["execution_status"] = "design_only_not_run"
    return result


def freeze_all_designs(source_sha: str) -> dict[str, Any]:
    if len(source_sha) != 40:
        raise ValueError("M3R design requires a full clean implementation SHA")
    training = training_design(source_sha)
    validation = validation_design(source_sha, training)
    candidates = candidate_pool(source_sha, training, validation)
    audit = discretization_audit_design(source_sha)
    train_set = {point_tuple(point) for point in training["points"]}
    validation_set = {point_tuple(point) for point in validation["points"]}
    candidate_set = {point_tuple(point) for point in candidates["points"]}
    audit_set = {point_tuple(point) for point in audit["points"]}
    intersections = {
        "training_validation": sorted(train_set & validation_set),
        "training_candidate": sorted(train_set & candidate_set),
        "validation_candidate": sorted(validation_set & candidate_set),
        "audit_training": sorted(audit_set & train_set),
        "audit_validation": sorted(audit_set & validation_set),
    }
    if any(intersections[name] for name in
           ("training_validation", "training_candidate", "validation_candidate")):
        raise RuntimeError(f"production design intersections are nonempty: {intersections}")
    split_hashes = {
        "schema_version": "task002.m3r-split-hashes.v1", "source_sha": source_sha,
        "training_sha256": training["point_tuple_sha256"],
        "frozen_validation_sha256": validation["point_tuple_sha256"],
        "candidate_pool_sha256": candidates["point_tuple_sha256"],
        "discretization_audit_sha256": audit["point_tuple_sha256"],
        "intersection_audit": intersections,
        "combined_design_sha256": canonical_hash({
            "training": training["point_tuple_sha256"],
            "validation": validation["point_tuple_sha256"],
            "candidates": candidates["point_tuple_sha256"],
            "audit": audit["point_tuple_sha256"], "source_sha": source_sha,
        }),
    }
    return {"training_design.json": training,
            "frozen_validation_design.json": validation,
            "candidate_pool.json": candidates,
            "discretization_audit_design.json": audit,
            "split_hashes.json": split_hashes}
