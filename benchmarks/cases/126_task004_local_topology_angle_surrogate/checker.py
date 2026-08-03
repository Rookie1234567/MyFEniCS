"""Independent, response-blind Case126 checker.

The checker reads immutable arrays and JSON contracts directly.  It does not
import the M4E model code, train a model, open a blind response, or execute a
forward solver.  Its purpose is to catch accidental dataset mutation and
qualification-contract mixing before review.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
PACKAGE = REPO / "benchmarks/artifacts/cases/125_task004_angle_training_qualification/train96"
OUTCOMES = REPO / "surrogate_tasks/task004_nominal_geometry_angle_surrogate/outcomes"
STRESS = REPO / "benchmarks/cases/125_task004_angle_training_qualification/outcomes/SPATIAL_HOLDOUT_WINDOWS.json"
TRAINING_DESIGN = REPO / "benchmarks/cases/123_task004_nominal_geometry_angle_surrogate/training_design.json"
OUT = ROOT / "records/case126_check.json"
FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
DATASET_ID = "task004_angle_nominal_p5_ny4_train96_v2"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def main() -> int:
    checks: dict[str, bool] = {}
    errors: list[str] = []

    required = [
        PACKAGE / "dataset_manifest.json", PACKAGE / "file_hashes.json",
        PACKAGE / "angles.npy", PACKAGE / "inputs.npy", PACKAGE / "aggregates.npy",
        PACKAGE / "order_powers.npy", PACKAGE / "power_carrying_mask.npy",
        OUTCOMES / "ANGLE_AGGREGATE_QUALIFICATION_CONTRACT.json",
        OUTCOMES / "ANGLE_ORDER_QUALIFICATION_CONTRACT.json",
        OUTCOMES / "SUPPORTED_INTERPOLATION_WINDOWS_V2.json",
        OUTCOMES / "ACTIVE_LEARNING_ELIGIBILITY.json", STRESS, TRAINING_DESIGN,
    ]
    checks["required_artifacts_present"] = all(path.is_file() for path in required)
    if not checks["required_artifacts_present"]:
        errors.append("required Case125/M4E artifact is missing")
        result = {"schema_version": "case126.check.v1", "status": "fail",
                  "checks": checks, "errors": errors}
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, indent=2))
        return 1

    manifest = json.loads((PACKAGE / "dataset_manifest.json").read_text())
    stored = json.loads((PACKAGE / "file_hashes.json").read_text())
    actual = {path.name: digest(path) for path in sorted(PACKAGE.iterdir())
              if path.is_file() and path.name != "file_hashes.json"}
    checks["train96_hashes_rebuild"] = stored == actual
    checks["train96_manifest_identity"] = (
        manifest.get("dataset_id") == DATASET_ID and
        manifest.get("sample_count") == 96 and
        manifest.get("forward_solver_sha") == FORWARD_SHA and
        manifest.get("immutable") is True and
        manifest.get("validation_target_accessed") is False and
        manifest.get("blind_validation_count") == 0
    )
    checks["train96_arrays_identity"] = True
    expected_arrays = {
        "angles.npy": ((96, 2), "float64"),
        "inputs.npy": ((96, 4), "float64"),
        "aggregates.npy": ((96, 4), "float64"),
        "order_powers.npy": ((96, 22, 2), "float64"),
        "power_carrying_mask.npy": ((96, 22, 2), "bool"),
    }
    for name, (shape, dtype) in expected_arrays.items():
        array = np.load(PACKAGE / name, allow_pickle=False)
        if tuple(array.shape) != shape or str(array.dtype) != dtype:
            checks["train96_arrays_identity"] = False
            errors.append(f"array identity mismatch: {name}")
    angles = np.load(PACKAGE / "angles.npy", allow_pickle=False)
    inputs = np.load(PACKAGE / "inputs.npy", allow_pickle=False)
    train_indices = np.load(PACKAGE / "train_indices.npy", allow_pickle=False)
    checks["nominal_geometry_and_angle_domain"] = bool(
        np.all(inputs[:, :2] == np.asarray([120.0, 17.0])) and
        np.min(angles[:, 0]) >= 0.5 and np.max(angles[:, 0]) <= 10.0 and
        np.min(angles[:, 1]) >= 0.0 and np.max(angles[:, 1]) <= 90.0 and
        np.array_equal(np.sort(train_indices), np.arange(96, dtype=np.int64))
    )
    design = json.loads(TRAINING_DESIGN.read_text())
    design_tuples = [[float(np.round(float(point[key]), 12)) for key in
                      ("height_nm", "width_x_nm", "grazing_deg", "azimuth_deg")]
                     for point in design.get("points", [])]
    package_tuples = inputs.round(12).tolist()
    checks["exact_training_design_identity"] = bool(
        design.get("point_count") == 96 and
        bool(design.get("source_sha")) and
        design.get("production_model_id") == "S_PROD_FULL3D_STATIC_P5_H10_NY4" and
        design.get("production_solver_route_id") == "full3d_static_uniform_n1curl_p5_h10_ny4" and
        design_tuples == package_tuples and
        manifest.get("training_tuple_sha256") == canonical(design_tuples)
    )

    aggregate = json.loads((OUTCOMES / "ANGLE_AGGREGATE_QUALIFICATION_CONTRACT.json").read_text())
    order = json.loads((OUTCOMES / "ANGLE_ORDER_QUALIFICATION_CONTRACT.json").read_text())
    active = json.loads((OUTCOMES / "ACTIVE_LEARNING_ELIGIBILITY.json").read_text())
    checks["aggregate_order_contracts_are_separate"] = bool(
        aggregate.get("level") == "A_aggregate_RTA" and
        order.get("level") == "B_order_resolved_power" and
        aggregate.get("level") != order.get("level") and
        aggregate.get("dataset_id") == DATASET_ID and
        order.get("dataset_id") == DATASET_ID and
        aggregate.get("forward_solver_sha") == FORWARD_SHA and
        order.get("forward_solver_sha") == FORWARD_SHA and
        aggregate.get("training_only") is True and order.get("training_only") is True and
        aggregate.get("validation_target_accessed") is False and
        order.get("validation_target_accessed") is False
    )
    allowed = {"local_rbf", "local_matern", "topology_expert", "trend_local_residual"}
    candidates = aggregate.get("candidate_results", [])
    checks["finite_m4e_candidate_set"] = bool(
        len(candidates) == 8 and
        all(item.get("family") in allowed for item in candidates) and
        aggregate.get("selected_candidate") in {item.get("candidate") for item in candidates}
    )
    checks["expected_qualification_outcomes"] = bool(
        aggregate.get("status") == "not_qualified_but_viable" and
        aggregate.get("qualified") is False and
        order.get("status") == "not_qualified" and
        order.get("qualified") is False
    )
    checks["active_learning_is_eligibility_only"] = bool(
        active.get("dataset_id") == DATASET_ID and
        active.get("forward_solver_sha") == FORWARD_SHA and
        active.get("validation_target_accessed") is False and
        active.get("candidate_pool_response_blind") is True and
        active.get("fem_started") is False and
        active.get("plan_status") == "eligibility_only_no_fem"
    )
    checks["no_model_lock_or_new_fem"] = not any(
        path.name.endswith("MODEL_SELECTION_LOCK.json") or
        path.name.endswith("MODEL_LOCK.json")
        for path in OUTCOMES.iterdir()
    ) and not any(path.name.startswith("fem") for path in (ROOT / "records").iterdir())

    windows = json.loads((OUTCOMES / "SUPPORTED_INTERPOLATION_WINDOWS_V2.json").read_text())
    expected_names = {"low_grazing", "high_azimuth", "cutoff_near", "ordinary_interior"}
    window_ok = True
    for item in windows.get("windows", []):
        indices = set(item.get("indices", []))
        support = item.get("support_indices", [])
        flattened_support = [int(value) for row in support for value in row]
        if (len(support) != len(indices) or
                any(len(row) != 6 for row in support) or
                len(set(flattened_support)) < len(indices) or
                indices.intersection(set(flattened_support)) or
                any(value != 6 for value in item.get("support_count_per_point", []))):
            window_ok = False
    stress_hash = digest(STRESS)
    checks["supported_windows_v2_frozen_and_supported"] = bool(
        windows.get("schema_version") == "task004.supported-interpolation-windows.v2" and
        {item.get("name") for item in windows.get("windows", [])} == expected_names and
        len(windows.get("windows", [])) == 4 and window_ok and
        windows.get("stress_authority", {}).get("sha256") == stress_hash and
        windows.get("stress_authority", {}).get("status") == "advisory_extrapolation_stress"
    )
    checks["old_extrapolation_stress_preserved"] = bool(
        json.loads(STRESS.read_text()).get("schema_version") == "task004.spatial-holdout-windows.v1"
    )
    checks["task003_and_validation_sealed"] = bool(
        manifest.get("validation_target_accessed") is False and
        not (PACKAGE / "sealed_validation_indices.npy").exists()
    )
    checks["all_checks"] = all(checks.values()) and not errors
    result = {
        "schema_version": "case126.check.v1", "status": "pass" if checks["all_checks"] else "fail",
        "checks": checks, "errors": errors, "training_count": 96,
        "dataset_id": DATASET_ID, "forward_solver_sha": FORWARD_SHA,
        "aggregate_status": aggregate.get("status"), "order_status": order.get("status"),
        "active_learning_eligibility": active.get("eligible_for_one_round_16_fem"),
        "fem_started": False, "validation_target_accessed": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if checks["all_checks"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
