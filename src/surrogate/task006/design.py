"""Frozen Task006 design and exact-reuse identity helpers.

This module contains only deterministic design bookkeeping.  It does not
launch a solver and it deliberately keeps the 12 blind tuples out of any
record loader used by the M0/M1 pipeline.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


FORWARD_SOLVER_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
OBSERVABLE_SCHEMA = "task002.fixed-n0-orders.v3"
PARAMETER_SCHEMA = "task002.s-p5-ny4-production-parameters.v3"
MOTHER_DATASET_ID = "task005_discrete_angle_hw_sensitivity_p5_ny4_v1"
TASK006_DATASET_ID = "task006_fixed_A05_A07_A09_hw_train37_p5_ny4_v1"
TASK005_LOCK = "surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/outcomes/DISCRETE_ILLUMINATION_FISHER_DOE_LOCK_V2.json"

ANGLES: tuple[tuple[str, float, float], ...] = (
    ("A05", 2.0, 0.0),
    ("A07", 2.0, 90.0),
    ("A09", 4.0, 60.0),
)

H_NODES: tuple[float, ...] = (115.0, 117.5, 118.75, 120.0, 121.25, 122.5, 125.0)
W_NODES: tuple[float, ...] = (16.0, 16.5, 16.75, 17.0, 17.25, 17.5, 18.0)

_CENTER: tuple[tuple[float, float], ...] = (
    (120.0, 17.0),
    (118.75, 17.0),
    (121.25, 17.0),
    (120.0, 16.75),
    (120.0, 17.25),
    (118.75, 16.75),
    (118.75, 17.25),
    (121.25, 17.25),
)
_COARSE_AXIS: tuple[tuple[float, float], ...] = (
    (117.5, 17.0),
    (122.5, 17.0),
    (120.0, 16.5),
    (120.0, 17.5),
)
_MISSING_QUADRANT: tuple[tuple[float, float], ...] = ((121.25, 16.75),)

BLIND_GEOMETRIES: tuple[tuple[float, float], ...] = (
    (117.5, 16.5), (117.5, 16.75), (117.5, 17.25), (117.5, 17.5),
    (118.75, 16.5), (118.75, 17.5),
    (121.25, 16.5), (121.25, 17.5),
    (122.5, 16.5), (122.5, 16.75), (122.5, 17.25), (122.5, 17.5),
)


def canonical_hash(value: Any) -> str:
    """Hash a JSON value using the repository's stable identity encoding."""

    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def all_mother_geometries() -> tuple[tuple[float, float], ...]:
    """Return the 49 tuples in deterministic row-major (h, then w) order."""

    return tuple((h, w) for h in H_NODES for w in W_NODES)


def is_boundary(geometry: tuple[float, float]) -> bool:
    h, w = geometry
    return h in (H_NODES[0], H_NODES[-1]) or w in (W_NODES[0], W_NODES[-1])


def _ordered_unique(values: Iterable[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    seen: set[tuple[float, float]] = set()
    result: list[tuple[float, float]] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


TRAIN_GEOMETRIES: tuple[tuple[float, float], ...] = _ordered_unique(
    [geometry for geometry in all_mother_geometries() if is_boundary(geometry)]
    + list(_CENTER) + list(_COARSE_AXIS) + list(_MISSING_QUADRANT)
)


def tuple_rows(geometries: Iterable[tuple[float, float]]) -> list[list[float]]:
    return [[float(h), float(w)] for h, w in geometries]


def angle_rows() -> list[dict[str, Any]]:
    return [
        {"angle_id": angle_id, "grazing_deg": grazing, "azimuth_deg": azimuth,
         "tuple": [grazing, azimuth]}
        for angle_id, grazing, azimuth in ANGLES
    ]


def train_membership(geometry: tuple[float, float]) -> str:
    if geometry in TRAIN_GEOMETRIES:
        return "training"
    if geometry in BLIND_GEOMETRIES:
        return "blind"
    return "invalid"


def expected_reuse_key(geometry: tuple[float, float], angle_id: str) -> str:
    return f"{geometry[0]:g},{geometry[1]:g}/{angle_id}"


def expected_reuse_sources(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Return exact existing record locations for the 8 complete tuples.

    The central geometry is stored in the immutable Task004 JSONL package;
    the other seven geometries are individual immutable Task005 records.
    Only these known paths are opened by the M0/M1 reuse loader.
    """

    root = repo_root.resolve()
    result: dict[str, dict[str, Any]] = {}
    angle_map = {angle_id: (grazing, azimuth) for angle_id, grazing, azimuth in ANGLES}
    center_jsonl = root / "benchmarks/artifacts/cases/127_task004_active_learning_round1/train112/sample_records.jsonl"
    for angle_id, (grazing, azimuth) in angle_map.items():
        result[expected_reuse_key((120.0, 17.0), angle_id)] = {
            "source_kind": "task004_train112_jsonl",
            "path": str(center_jsonl), "line_match": [120.0, 17.0, grazing, azimuth],
        }

    half_map = {
        (118.75, 17.0): "H-", (121.25, 17.0): "H+",
        (120.0, 16.75): "W-", (120.0, 17.25): "W+",
    }
    for geometry, state in half_map.items():
        for angle_id, _, _ in ANGLES:
            if angle_id == "A05":
                # A05 half-step records were generated in the Task005 M2
                # campaign; A07/A09 remain the immutable M1 audit records.
                path = root / f"benchmarks/artifacts/cases/132_task005_sensitivity_dataset/m2/A05/{state}/task005_production_sample.json"
                source_kind = "task005_m2_sensitivity"
            else:
                path = root / f"benchmarks/artifacts/cases/131_task005_design_and_step_audit/m1/{angle_id}/half/{state}/task005_production_sample.json"
                source_kind = "task005_m1_half"
            result[expected_reuse_key(geometry, angle_id)] = {
                "source_kind": source_kind,
                "path": str(path), "line_match": None,
            }

    g_map = {
        (118.75, 16.75): "G1", (121.25, 17.25): "G2", (118.75, 17.25): "G3",
    }
    for geometry, group in g_map.items():
        for angle_id, _, _ in ANGLES:
            path = root / f"benchmarks/artifacts/cases/133_task005_off_centre_recovery/m4/{group}/{angle_id}/task005_production_sample.json"
            result[expected_reuse_key(geometry, angle_id)] = {
                "source_kind": "task005_m4_off_centre",
                "path": str(path), "line_match": None,
            }

    coarse_state = {
        (117.5, 17.0): "H-", (122.5, 17.0): "H+",
        (120.0, 16.5): "W-", (120.0, 17.5): "W+",
    }
    for geometry, state in coarse_state.items():
        for angle_id in ("A07", "A09"):
            path = root / f"benchmarks/artifacts/cases/131_task005_design_and_step_audit/m1/{angle_id}/coarse/{state}/task005_production_sample.json"
            result[expected_reuse_key(geometry, angle_id)] = {
                "source_kind": "task005_m1_coarse",
                "path": str(path), "line_match": None,
            }
    return result


def design_payload(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    lock_path = root / TASK005_LOCK
    lock_sha = file_hash(lock_path)
    mother = tuple_rows(all_mother_geometries())
    train = tuple_rows(TRAIN_GEOMETRIES)
    blind = tuple_rows(BLIND_GEOMETRIES)
    return {
        "schema_version": "task006.hw-mother-grid.v1",
        "status": "frozen",
        "created_without_fem": True,
        "dataset_id": TASK006_DATASET_ID,
        "forward_solver_sha": FORWARD_SOLVER_SHA,
        "model_id": MODEL_ID,
        "solver_route_id": ROUTE_ID,
        "observable_schema_version": OBSERVABLE_SCHEMA,
        "parameter_schema_version": PARAMETER_SCHEMA,
        "fixed_illumination": angle_rows(),
        "height_nodes_nm": list(H_NODES), "width_nodes_nm": list(W_NODES),
        "mother_count": len(mother), "mother_geometries": mother,
        "mother_tuple_sha256": canonical_hash(mother),
        "training_count": len(train), "training_geometries": train,
        "training_tuple_sha256": canonical_hash(train),
        "blind_count": len(blind), "blind_geometries": blind,
        "blind_tuple_sha256": canonical_hash(blind),
        "partition_identity": canonical_hash({"training": train, "blind": blind}),
        "partition_rule": "all 24 boundary points + frozen 8 center/near-center + 4 coarse-axis + 1 missing quadrant; remaining 12 interior points blind",
        "task005_v2_lock": {"path": TASK005_LOCK, "sha256": lock_sha},
        "blind_response_accessed": False,
        "new_fem_count": 0,
    }


def training_payload(repo_root: Path) -> dict[str, Any]:
    return {
        "schema_version": "task006.hw-train37-design.v1",
        "status": "frozen",
        "dataset_id": TASK006_DATASET_ID,
        "forward_solver_sha": FORWARD_SOLVER_SHA,
        "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
        "observable_schema_version": OBSERVABLE_SCHEMA,
        "fixed_angle_order": [row[0] for row in ANGLES],
        "geometry_count": len(TRAIN_GEOMETRIES),
        "geometries": tuple_rows(TRAIN_GEOMETRIES),
        "tuple_sha256": canonical_hash(tuple_rows(TRAIN_GEOMETRIES)),
        "per_angle_record_count": len(TRAIN_GEOMETRIES) * len(ANGLES),
        "expected_new_fem_count": 79,
        "reuse_record_count": 32,
        "new_record_count": 79,
        "new_record_breakdown": {
            "boundary_geometries_times_three_angles": 72,
            "coarse_axis_A05_only": 4,
            "missing_quadrant_times_three_angles": 3,
        },
        "reuse_policy": "8 complete geometry tuples x 3 angles plus 4 coarse-axis A07/A09 records; exact source/config/schema match only",
        "blind_response_accessed": False,
        "repo_root_for_sources": str(repo_root.resolve()),
    }


def blind_payload() -> dict[str, Any]:
    blind = tuple_rows(BLIND_GEOMETRIES)
    return {
        "schema_version": "task006.hw-blind12-design.v1",
        "status": "frozen_not_run",
        "dataset_id": TASK006_DATASET_ID,
        "fixed_angle_order": [row[0] for row in ANGLES],
        "count": len(BLIND_GEOMETRIES),
        "geometries": blind,
        "tuple_sha256": canonical_hash(blind),
        "all_strictly_interior": all(not is_boundary(tuple(row)) for row in blind),
        "fem_run": False,
        "responses_accessed": False,
        "access_policy": "do not open, search, or approximate-match blind responses before review authorization",
    }


def reuse_payload(repo_root: Path) -> dict[str, Any]:
    sources = expected_reuse_sources(repo_root)
    records = []
    for geometry in TRAIN_GEOMETRIES:
        for angle_id, grazing, azimuth in ANGLES:
            key = expected_reuse_key(geometry, angle_id)
            source = sources.get(key)
            records.append({
                "key": key, "height_nm": geometry[0], "width_nm": geometry[1],
                "angle_id": angle_id, "grazing_deg": grazing, "azimuth_deg": azimuth,
                "reuse": source is not None,
                "source_kind": source["source_kind"] if source else None,
                "source_path": source["path"] if source else None,
                "line_match": source["line_match"] if source else None,
                "source_sha_required": FORWARD_SOLVER_SHA,
                "observable_schema_required": OBSERVABLE_SCHEMA,
                "status": "reserved_reuse" if source else "reserved_new_fem",
            })
    return {
        "schema_version": "task006.hw-exact-reuse-inventory.v1",
        "status": "frozen",
        "dataset_id": TASK006_DATASET_ID,
        "forward_solver_sha": FORWARD_SOLVER_SHA,
        "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
        "observable_schema_version": OBSERVABLE_SCHEMA,
        "expected_complete_reuse_geometries": [list(g) for g in ((120.0,17.0),(118.75,17.0),(121.25,17.0),(120.0,16.75),(120.0,17.25),(118.75,16.75),(118.75,17.25),(121.25,17.25))],
        "expected_partial_reuse_geometries": [list(g) for g in _COARSE_AXIS],
        "expected_new_geometry_count": 37 - 8,
        "records": records,
        "reuse_count": sum(1 for row in records if row["reuse"]),
        "new_record_count": sum(1 for row in records if not row["reuse"]),
        "new_fem_count": 79,
        "blind_response_accessed": False,
    }
