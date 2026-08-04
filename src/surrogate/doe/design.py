"""Task005 M0: frozen discrete-angle and perturbation contracts.

M0 is intentionally response-blind apart from reading the already immutable
Task004 train112 package.  It does not open frozen validation data and does
not invoke a FEM executable.  The design is a short, deterministic manifest
that identifies the nominal sample to reuse at each angle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


FORWARD_SOLVER_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
OBSERVABLE_SCHEMA = "task002.fixed-n0-orders.v3"
PARAMETER_SCHEMA = "task002.s-p5-ny4-production-parameters.v3"
TRAIN_DATASET_ID = "task004_angle_nominal_p5_ny4_train112_v1"
TRAIN_TUPLE_SHA256 = "00fb746bbb881ac7fc3cd27c313b2b526bd2f69f8e89ef621f3e6d9790af5c68"
M0_DESIGN_SCHEMA = "task005.discrete-angle-design.v1"
PERTURBATION_SCHEMA = "task005.central-finite-difference.v1"

# This order is part of the task contract.  Never sort this tuple by a
# convenience criterion: the IDs are used in later manifests and hashes.
ANGLE_CANDIDATES: tuple[tuple[str, float, float], ...] = (
    ("A00", 0.5, 0.0), ("A01", 0.5, 45.0), ("A02", 0.5, 90.0),
    ("A03", 1.0, 15.0), ("A04", 1.0, 60.0),
    ("A05", 2.0, 0.0), ("A06", 2.0, 45.0), ("A07", 2.0, 90.0),
    ("A08", 4.0, 15.0), ("A09", 4.0, 60.0), ("A10", 4.0, 90.0),
    ("A11", 6.0, 30.0), ("A12", 6.0, 75.0),
    ("A13", 8.0, 45.0), ("A14", 10.0, 0.0), ("A15", 10.0, 90.0),
)
AUDIT_ANGLE_IDS = ("A00", "A07", "A09", "A14", "A15")
BASELINE_PAIR = ("A14", "A15")
H0 = 120.0
W0 = 17.0
WAVELENGTH_NM = 13.5


def canonical_hash(value: Any) -> str:
    """Hash JSON values with one canonical representation."""

    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _float_tuple(values: Any) -> tuple[float, ...]:
    return tuple(float(np.round(float(value), 12)) for value in values)


def _load_train112(train_dir: Path) -> tuple[dict[str, Any], np.ndarray,
                                                 np.ndarray, np.ndarray, list[dict[str, Any]]]:
    manifest = json.loads((train_dir / "dataset_manifest.json").read_text())
    angles = np.load(train_dir / "angles.npy", allow_pickle=False)
    inputs = np.load(train_dir / "inputs.npy", allow_pickle=False)
    sample_ids = np.load(train_dir / "sample_ids.npy", allow_pickle=False)
    records = [json.loads(line) for line in
               (train_dir / "sample_records.jsonl").read_text().splitlines() if line.strip()]
    if angles.shape != (112, 2) or inputs.shape != (112, 4) or sample_ids.shape != (112,):
        raise ValueError("Task004 train112 array shape identity is not (112, ...)")
    if len(records) != 112:
        raise ValueError("Task004 train112 record count is not 112")
    return manifest, angles, inputs, sample_ids, records


def _validate_immutable_train(manifest: dict[str, Any], train_dir: Path,
                              angles: np.ndarray, inputs: np.ndarray,
                              sample_ids: np.ndarray,
                              records: list[dict[str, Any]]) -> dict[str, Any]:
    required = {
        "dataset_id": TRAIN_DATASET_ID,
        "training_count": 112,
        "sample_count": 112,
        "forward_solver_sha": FORWARD_SOLVER_SHA,
        "source_sha": FORWARD_SOLVER_SHA,
        "model_id": MODEL_ID,
        "solver_route_id": ROUTE_ID,
        "observable_schema_version": OBSERVABLE_SCHEMA,
        "parameter_schema_version": PARAMETER_SCHEMA,
        "incident_polarization": "S",
        "wavelength_nm": WAVELENGTH_NM,
        "validation_target_accessed": False,
        "immutable": True,
        "source_dirty": False,
        "training_tuple_sha256": TRAIN_TUPLE_SHA256,
    }
    mismatches = {
        key: {"expected": value, "actual": manifest.get(key)}
        for key, value in required.items() if manifest.get(key) != value
    }
    if mismatches:
        raise ValueError(f"immutable train112 manifest mismatch: {mismatches}")
    if np.any(~np.isfinite(angles)) or np.any(~np.isfinite(inputs)):
        raise ValueError("train112 angles/inputs contain non-finite values")
    if not np.allclose(inputs[:, :2], np.asarray([H0, W0]), rtol=0.0, atol=0.0):
        raise ValueError("train112 nominal geometry is not exactly (120,17) nm")
    by_sample_id = {str(row.get("sample_id")): row for row in records}
    if set(map(str, sample_ids.tolist())) != set(by_sample_id):
        raise ValueError("sample_ids.npy and sample_records.jsonl disagree")
    if any(row.get("status") != "measured_pass" for row in records):
        raise ValueError("train112 contains a non-passing nominal record")
    if any(row.get("source_sha") != FORWARD_SOLVER_SHA or row.get("source_dirty") is not False
           for row in records):
        raise ValueError("train112 records are not bound to the immutable forward SHA")
    hashes_path = train_dir / "file_hashes.json"
    expected_hashes = json.loads(hashes_path.read_text())
    actual_hashes = {
        path.name: file_sha256(path) for path in sorted(train_dir.iterdir())
        if path.is_file() and path.name != hashes_path.name
    }
    if actual_hashes != expected_hashes:
        raise ValueError("train112 file hash package is not immutable")
    return {
        "dataset_id": manifest["dataset_id"],
        "training_tuple_sha256": manifest["training_tuple_sha256"],
        "sample_ids_hash": manifest.get("sample_ids_hash"),
        "manifest_sha256": file_sha256(train_dir / "dataset_manifest.json"),
        "file_hashes_sha256": file_sha256(hashes_path),
        "record_count": len(records),
        "validation_target_accessed": False,
    }


def _candidate_rows(angles: np.ndarray, inputs: np.ndarray,
                    sample_ids: np.ndarray,
                    records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records_by_id = {str(row["sample_id"]): row for row in records}
    rows: list[dict[str, Any]] = []
    for angle_id, grazing, azimuth in ANGLE_CANDIDATES:
        matches = np.flatnonzero(
            np.all(np.isclose(angles, np.asarray([grazing, azimuth]), atol=0.0, rtol=0.0), axis=1)
        )
        if len(matches) != 1:
            raise ValueError(f"{angle_id} nominal tuple count is {len(matches)}, expected one")
        index = int(matches[0])
        sample_id = str(sample_ids[index])
        record = records_by_id[sample_id]
        point_tuple = [H0, W0, float(grazing), float(azimuth)]
        rows.append({
            "angle_id": angle_id, "design_index": len(rows),
            "grazing_deg": float(grazing), "azimuth_deg": float(azimuth),
            "point_tuple": point_tuple,
            "point_hash": canonical_hash({"angle_id": angle_id, "point_tuple": point_tuple}),
            "train_index": index, "sample_id": sample_id,
            "record_formal_record_sha256": record.get("formal_record_sha256"),
            "record_execution_sha256": record.get("execution_sha256"),
            "source_sha": record.get("source_sha"),
            "config_hash": record.get("config_hash"),
            "topology_hash": record.get("topology_hash"),
            "status": record.get("status"),
            "reuse": "immutable_train112_nominal_no_rerun",
        })
    if len({row["sample_id"] for row in rows}) != 16:
        raise ValueError("candidate nominal samples are not all distinct")
    return rows


def build_m0_artifacts(*, outcomes_dir: Path, train_dir: Path,
                       task004_status_path: Path,
                       implementation_sha: str = "working-tree-pending") -> dict[str, Any]:
    """Create the three immutable M0 manifests and return their payloads."""

    manifest, angles, inputs, sample_ids, records = _load_train112(train_dir)
    train_identity = _validate_immutable_train(
        manifest, train_dir, angles, inputs, sample_ids, records,
    )
    task004_status = json.loads(task004_status_path.read_text())
    if task004_status.get("status") != "closed_controlled_negative":
        raise ValueError("Task004 is not closed_controlled_negative")
    if task004_status.get("blind_validation", {}).get("count", 0) != 0:
        raise ValueError("Task004 blind validation is not the required not-run state")
    rows = _candidate_rows(angles, inputs, sample_ids, records)
    tuples = [row["point_tuple"] for row in rows]
    design = {
        "schema_version": M0_DESIGN_SCHEMA,
        "design_id": "task005_discrete_angle_candidates_v1",
        "status": "frozen",
        "created_without_fem": True,
        "new_fem_count": 0,
        "implementation_sha": implementation_sha,
        "forward_solver_sha": FORWARD_SOLVER_SHA,
        "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
        "observable_schema_version": OBSERVABLE_SCHEMA,
        "parameter_schema_version": PARAMETER_SCHEMA,
        "fixed_parameters": {
            "height_nm": H0, "width_x_nm": W0,
            "wavelength_nm": WAVELENGTH_NM, "polarization": "S",
        },
        "candidate_order": [row[0] for row in ANGLE_CANDIDATES],
        "point_tuple_semantics": "(height_nm,width_nm,grazing_deg,azimuth_deg), rounded to 12 decimals",
        "point_tuple_sha256": canonical_hash(tuples),
        "audit_angle_ids": list(AUDIT_ANGLE_IDS),
        "baseline_pair": list(BASELINE_PAIR),
        "train112": train_identity,
        "points": rows,
        "frozen_validation_access": False,
        "task004_status_sha256": file_sha256(task004_status_path),
    }
    perturbation = {
        "schema_version": PERTURBATION_SCHEMA,
        "status": "frozen",
        "implementation_sha": implementation_sha,
        "forward_solver_sha": FORWARD_SOLVER_SHA,
        "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
        "nominal": {"height_nm": H0, "width_nm": W0},
        "allowed_domain": {"height_nm": [115.0, 125.0], "width_nm": [16.0, 18.0]},
        "steps": {
            "coarse": {"delta_h_nm": 2.5, "delta_w_nm": 0.5},
            "half": {"delta_h_nm": 1.25, "delta_w_nm": 0.25},
        },
        "states": {
            "H-": {"height_offset_sign": -1, "width_offset_sign": 0},
            "H+": {"height_offset_sign": 1, "width_offset_sign": 0},
            "W-": {"height_offset_sign": 0, "width_offset_sign": -1},
            "W+": {"height_offset_sign": 0, "width_offset_sign": 1},
        },
        "derivative": "central: (plus-minus)/(2*delta), physical nm^{-1}",
        "production_selection": "independently lock delta_h and delta_w after M1; Richardson is diagnostic only",
        "max_m1_new_fem": 40,
        "m1_audit_angle_ids": list(AUDIT_ANGLE_IDS),
        "frozen_validation_access": False,
    }
    reuse = {
        "schema_version": "task005.nominal-reuse-report.v1",
        "status": "pass",
        "implementation_sha": implementation_sha,
        "source_dataset_id": TRAIN_DATASET_ID,
        "source_training_tuple_sha256": TRAIN_TUPLE_SHA256,
        "source_manifest_sha256": train_identity["manifest_sha256"],
        "forward_solver_sha": FORWARD_SOLVER_SHA,
        "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
        "nominal_reuse_policy": "read-only train112 formal records; no central-geometry rerun",
        "candidate_count": len(rows), "exactly_one_each": True,
        "all_status_measured_pass": True,
        "validation_target_accessed": False,
        "task004_blind24_run": False,
        "points": [{key: row[key] for key in (
            "angle_id", "train_index", "sample_id", "point_tuple", "status",
            "record_formal_record_sha256", "record_execution_sha256", "config_hash",
            "topology_hash", "reuse") } for row in rows],
    }
    outcomes_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "DISCRETE_ANGLE_DESIGN.json": design,
        "PERTURBATION_SCHEMA.json": perturbation,
        "NOMINAL_REUSE_REPORT.json": reuse,
    }
    for name, payload in payloads.items():
        (outcomes_dir / name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        )
    return payloads


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcomes", type=Path, required=True)
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--task004-status", type=Path, required=True)
    parser.add_argument("--implementation-sha", default="working-tree-pending")
    args = parser.parse_args()
    build_m0_artifacts(
        outcomes_dir=args.outcomes.resolve(), train_dir=args.train_dir.resolve(),
        task004_status_path=args.task004_status.resolve(),
        implementation_sha=args.implementation_sha,
    )
    print("Task005 M0 manifests written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
