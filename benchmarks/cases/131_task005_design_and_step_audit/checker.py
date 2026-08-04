"""Independent Task005 M0 checker.

The checker intentionally duplicates the small identity calculations instead
of importing ``src.surrogate.doe.design``.  It reads only the immutable
Task004 train112 package and Task004 closeout status; no validation response
or FEM command is opened or launched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
TRAIN_ID = "task004_angle_nominal_p5_ny4_train112_v1"
TRAIN_TUPLE_SHA = "00fb746bbb881ac7fc3cd27c313b2b526bd2f69f8e89ef621f3e6d9790af5c68"
OBSERVABLE = "task002.fixed-n0-orders.v3"
PARAMETER_SCHEMA = "task002.s-p5-ny4-production-parameters.v3"
ANGLES = (
    ("A00", 0.5, 0.0), ("A01", 0.5, 45.0), ("A02", 0.5, 90.0),
    ("A03", 1.0, 15.0), ("A04", 1.0, 60.0),
    ("A05", 2.0, 0.0), ("A06", 2.0, 45.0), ("A07", 2.0, 90.0),
    ("A08", 4.0, 15.0), ("A09", 4.0, 60.0), ("A10", 4.0, 90.0),
    ("A11", 6.0, 30.0), ("A12", 6.0, 75.0),
    ("A13", 8.0, 45.0), ("A14", 10.0, 0.0), ("A15", 10.0, 90.0),
)


def canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(*, outcomes: Path, train: Path, task004_status: Path) -> tuple[dict[str, bool], list[str]]:
    checks: dict[str, bool] = {}
    errors: list[str] = []
    required = [outcomes / name for name in (
        "DISCRETE_ANGLE_DESIGN.json", "PERTURBATION_SCHEMA.json",
        "NOMINAL_REUSE_REPORT.json")]
    checks["required_m0_outputs"] = all(path.is_file() for path in required)
    if not checks["required_m0_outputs"]:
        errors.append("one or more M0 manifests are missing")
        return checks, errors
    try:
        design = json.loads((outcomes / "DISCRETE_ANGLE_DESIGN.json").read_text())
        perturbation = json.loads((outcomes / "PERTURBATION_SCHEMA.json").read_text())
        reuse = json.loads((outcomes / "NOMINAL_REUSE_REPORT.json").read_text())
        manifest = json.loads((train / "dataset_manifest.json").read_text())
        stored = json.loads((train / "file_hashes.json").read_text())
        angles = np.load(train / "angles.npy", allow_pickle=False)
        inputs = np.load(train / "inputs.npy", allow_pickle=False)
        sample_ids = np.load(train / "sample_ids.npy", allow_pickle=False)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"M0 input read failed: {exc}")
        return checks, errors

    actual = {path.name: digest(path) for path in sorted(train.iterdir())
              if path.is_file() and path.name != "file_hashes.json"}
    checks["train112_hashes_recomputed"] = actual == stored
    checks["train112_array_identity"] = bool(
        angles.shape == (112, 2) and inputs.shape == (112, 4) and sample_ids.shape == (112,)
        and str(angles.dtype) == "float64" and str(inputs.dtype) == "float64"
        and np.all(inputs[:, :2] == np.asarray([120.0, 17.0]))
    )
    checks["train112_manifest_identity"] = bool(
        manifest.get("dataset_id") == TRAIN_ID and manifest.get("sample_count") == 112
        and manifest.get("training_count") == 112
        and manifest.get("forward_solver_sha") == FORWARD_SHA
        and manifest.get("source_sha") == FORWARD_SHA
        and manifest.get("source_dirty") is False and manifest.get("immutable") is True
        and manifest.get("validation_target_accessed") is False
        and manifest.get("blind_validation_count") == 0
        and manifest.get("training_tuple_sha256") == TRAIN_TUPLE_SHA
    )
    checks["design_identity"] = bool(
        design.get("schema_version") == "task005.discrete-angle-design.v1"
        and design.get("design_id") == "task005_discrete_angle_candidates_v1"
        and design.get("status") == "frozen"
        and design.get("created_without_fem") is True
        and design.get("new_fem_count") == 0
        and design.get("forward_solver_sha") == FORWARD_SHA
        and design.get("model_id") == MODEL_ID and design.get("solver_route_id") == ROUTE_ID
        and design.get("observable_schema_version") == OBSERVABLE
        and design.get("parameter_schema_version") == PARAMETER_SCHEMA
        and design.get("frozen_validation_access") is False
    )
    expected_ids = [row[0] for row in ANGLES]
    rows = design.get("points", [])
    checks["exact_16_design_order"] = bool(
        len(rows) == 16 and [row.get("angle_id") for row in rows] == expected_ids
        and design.get("candidate_order") == expected_ids
        and design.get("baseline_pair") == ["A14", "A15"]
        and design.get("audit_angle_ids") == ["A00", "A07", "A09", "A14", "A15"]
    )
    expected_tuples = [[120.0, 17.0, g, a] for _, g, a in ANGLES]
    checks["design_tuple_hash"] = bool(
        design.get("point_tuple_sha256") == canonical(expected_tuples)
        and [row.get("point_tuple") for row in rows] == expected_tuples
    )
    tuple_matches: list[bool] = []
    sample_matches: list[bool] = []
    for row, (_, grazing, azimuth) in zip(rows, ANGLES):
        matching = np.flatnonzero(np.all(
            np.isclose(angles, np.asarray([grazing, azimuth]), rtol=0.0, atol=0.0), axis=1))
        tuple_matches.append(len(matching) == 1)
        if len(matching) == 1:
            index = int(matching[0])
            sample_matches.append(row.get("train_index") == index
                                  and row.get("sample_id") == str(sample_ids[index]))
        else:
            sample_matches.append(False)
    checks["nominal_tuple_exactly_once"] = bool(all(tuple_matches))
    checks["nominal_reuse_sample_identity"] = bool(all(sample_matches)
        and len({row.get("sample_id") for row in rows}) == 16
        and all(row.get("reuse") == "immutable_train112_nominal_no_rerun" for row in rows))
    checks["perturbation_schema"] = bool(
        perturbation.get("schema_version") == "task005.central-finite-difference.v1"
        and perturbation.get("status") == "frozen"
        and perturbation.get("nominal") == {"height_nm": 120.0, "width_nm": 17.0}
        and perturbation.get("allowed_domain") == {
            "height_nm": [115.0, 125.0], "width_nm": [16.0, 18.0]}
        and perturbation.get("steps", {}).get("coarse") == {"delta_h_nm": 2.5, "delta_w_nm": 0.5}
        and perturbation.get("steps", {}).get("half") == {"delta_h_nm": 1.25, "delta_w_nm": 0.25}
        and set(perturbation.get("states", {})) == {"H-", "H+", "W-", "W+"}
        and perturbation.get("frozen_validation_access") is False
    )
    checks["nominal_reuse_report"] = bool(
        reuse.get("schema_version") == "task005.nominal-reuse-report.v1"
        and reuse.get("status") == "pass" and reuse.get("candidate_count") == 16
        and reuse.get("exactly_one_each") is True
        and reuse.get("validation_target_accessed") is False
        and reuse.get("task004_blind24_run") is False
        and len(reuse.get("points", [])) == 16
    )
    try:
        closeout = json.loads(task004_status.read_text())
        checks["task004_closed_and_blind_not_run"] = bool(
            closeout.get("status") == "closed_controlled_negative"
            and closeout.get("blind_validation", {}).get("status") == "intentionally_not_run"
            and closeout.get("blind_validation", {}).get("responses_accessed") is False
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        checks["task004_closed_and_blind_not_run"] = False
        errors.append(f"Task004 closeout read failed: {exc}")
    checks["m0_no_fem_claim"] = bool(
        design.get("new_fem_count") == 0 and design.get("created_without_fem") is True
        and reuse.get("nominal_reuse_policy") == "read-only train112 formal records; no central-geometry rerun"
    )
    if not all(checks.values()):
        errors.extend(f"failed:{key}" for key, value in checks.items() if not value)
    return checks, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outcomes", type=Path, default=Path("surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/outcomes"))
    parser.add_argument("--train", type=Path, default=Path("benchmarks/artifacts/cases/127_task004_active_learning_round1/train112"))
    parser.add_argument("--task004-status", type=Path, default=Path("surrogate_tasks/task004_nominal_geometry_angle_surrogate/TASK004_FINAL_STATUS.json"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/cases/131_task005_design_and_step_audit/records/case131_m0_check.json"))
    args = parser.parse_args()
    checks, errors = check(outcomes=args.outcomes.resolve(), train=args.train.resolve(), task004_status=args.task004_status.resolve())
    result = {"schema_version": "task005.case131-m0-check.v1", "status": "pass" if all(checks.values()) else "failed", "checks": checks, "errors": errors, "frozen_validation_accessed": False, "new_fem_count": 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
