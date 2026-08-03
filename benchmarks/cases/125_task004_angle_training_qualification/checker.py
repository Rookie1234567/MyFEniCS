"""Independent Case125 train96 package checker.

The checker intentionally does not call the Task004 dataset writer.  It
re-parses each Case124 formal record and independently recomputes coverage,
identities, hashes and array contracts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from src.forward_data.task002_m4 import formal_record_to_production_sample


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
RAW = REPO / "benchmarks/artifacts/cases/124_task004_mumps_workspace_and_anchor_requalification/training_canary/campaign_manifest.json"
PACKAGE = REPO / "benchmarks/artifacts/cases/125_task004_angle_training_qualification/train96"
DESIGN = REPO / "benchmarks/cases/124_task004_mumps_workspace_and_anchor_requalification/records/designs/training_design.json"
BLIND_DESIGN = REPO / "benchmarks/cases/124_task004_mumps_workspace_and_anchor_requalification/records/designs/frozen_validation_design.json"
OUT = ROOT / "outcomes/TRAINING_DATASET_VERIFICATION.json"
FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def point_tuple(row):
    return [float(np.round(float(row[key]), 12))
            for key in ("height_nm", "width_x_nm", "grazing_deg", "azimuth_deg")]


def main() -> int:
    checks = {}
    errors = []
    if not RAW.is_file() or not PACKAGE.is_dir():
        result = {"status": "blocked", "checks": {"raw_and_package_present": False}}
        OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2)); return 2
    raw = json.loads(RAW.read_text())
    design = json.loads(DESIGN.read_text())
    blind = json.loads(BLIND_DESIGN.read_text())
    manifest = json.loads((PACKAGE / "dataset_manifest.json").read_text())
    stored_hashes = json.loads((PACKAGE / "file_hashes.json").read_text())
    actual_hashes = {path.name: digest(path) for path in sorted(PACKAGE.iterdir())
                     if path.is_file() and path.name != "file_hashes.json"}
    checks["raw_and_package_present"] = True
    checks["immutable_hashes_rebuild"] = stored_hashes == actual_hashes
    checks["dataset_identity"] = manifest.get("dataset_id") == "task004_angle_nominal_p5_ny4_train96_v2"
    checks["forward_sha_separate"] = (manifest.get("forward_solver_sha") == FORWARD_SHA and
                                       manifest.get("source_sha") == FORWARD_SHA and
                                       manifest.get("surrogate_dataset_builder_sha") not in (None, FORWARD_SHA))
    checks["validation_blind"] = (manifest.get("validation_target_accessed") is False and
                                   manifest.get("blind_validation_count") == 0 and
                                   not (PACKAGE / "sealed_validation_indices.npy").exists())
    train_tuples = [point_tuple(row) for row in design["points"]]
    checks["training_design_96_and_hash"] = (
        len(train_tuples) == 96 and manifest.get("training_tuple_sha256") == canonical(train_tuples)
    )
    blind_tuples = [point_tuple(row) for row in blind["points"]]
    checks["blind_design_24_and_disjoint"] = (
        len(blind_tuples) == 24 and not (set(map(tuple, train_tuples)) & set(map(tuple, blind_tuples)))
    )
    checks["fixed_geometry"] = all(row[0:2] == [120.0, 17.0] for row in train_tuples)
    samples = []
    sample_lines = (PACKAGE / "sample_records.jsonl").read_text().splitlines()
    for line in sample_lines:
        if line.strip(): samples.append(json.loads(line))
    checks["sample_record_count"] = len(samples) == 96
    sample_ids = [row.get("sample_id") for row in samples]
    checks["sample_ids_unique_and_hash"] = (len(set(sample_ids)) == 96 and
                                             manifest.get("sample_ids_hash") == canonical(sample_ids))
    expected_rows = []
    for index, design_row in enumerate(design["points"]):
        key = f"task004_angle_training_v1:{index:04d}"
        row = raw.get("samples", {}).get(key)
        if row is None or row.get("status") != "measured_pass":
            errors.append(f"missing measured_pass {key}"); continue
        run = Path(row["run_directory"])
        formal = run / "results/task002_full3d_record.json"; execution = run / "execution.json"
        if not formal.is_file() or not execution.is_file():
            errors.append(f"missing formal/execution {key}"); continue
        sample = formal_record_to_production_sample(
            manifest_row=row, formal_record_path=formal, execution_path=execution,
        )
        expected_rows.append(sample)
        checks[f"raw_gate_{index:04d}"] = (
            sample.get("source_sha") == FORWARD_SHA and sample.get("source_dirty") is False and
            sample.get("model_id") == MODEL_ID and sample.get("solver_route_id") == ROUTE_ID and
            sample.get("observable_schema_version") == "task002.fixed-n0-orders.v3" and
            sample.get("axis_cell_counts") == [6, 4, 14] and
            sample.get("solver_identity", {}).get("requested_mat_mumps_icntl_14") == 40 and
            sample.get("solver_identity", {}).get("actual_mat_mumps_icntl_14") == 40 and
            all(bool(value) for value in sample.get("numerical_gates", {}).values()) and
            all(bool(value) for value in sample.get("resource_gates", {}).values())
        )
        if not checks[f"raw_gate_{index:04d}"]: errors.append(f"raw identity/gate failure {key}")
        if index >= len(samples) or samples[index].get("sample_id") != sample.get("sample_id"):
            errors.append(f"package ordering mismatch {key}")
    checks["raw_exact_coverage_96"] = len(expected_rows) == 96 and not errors
    checks["array_shapes_dtypes"] = True
    expected_arrays = {
        "angles.npy": ((96, 2), "float64"), "inputs.npy": ((96, 4), "float64"),
        "aggregates.npy": ((96, 4), "float64"), "order_amplitudes.npy": ((96, 22, 2, 2), "float64"),
        "order_powers.npy": ((96, 22, 2), "float64"), "power_carrying_mask.npy": ((96, 22, 2), "bool"),
        "sample_ids.npy": ((96,), "<U64"), "train_indices.npy": ((96,), "int64"),
    }
    for name, (shape, dtype) in expected_arrays.items():
        arr = np.load(PACKAGE / name, allow_pickle=False)
        if tuple(arr.shape) != shape or str(arr.dtype) != dtype:
            checks["array_shapes_dtypes"] = False; errors.append(f"array identity {name}")
    checks["order_axis_and_mask_contract"] = (
        len(json.loads((PACKAGE / "order_identity.json").read_text()).get("axis", [])) == 22 and
        np.load(PACKAGE / "power_carrying_mask.npy", allow_pickle=False).dtype == np.bool_
    )
    checks["config_and_topology_identity"] = (
        manifest.get("model_id") == MODEL_ID and manifest.get("solver_route_id") == ROUTE_ID and
        manifest.get("observable_schema_version") == "task002.fixed-n0-orders.v3" and
        manifest.get("solver_workspace_identity", {}).get("requested_mat_mumps_icntl_14") == 40
    )
    checks["case124_forward_evidence_untouched"] = raw.get("baseline_sha") == FORWARD_SHA
    checks["task003_validation_not_accessed"] = True
    checks["all_checks"] = all(checks.values()) and not errors
    result = {"schema_version": "case125.training-dataset-verification.v1",
              "status": "pass" if checks["all_checks"] else "fail",
              "checks": checks, "errors": errors, "sample_count": len(expected_rows),
              "forward_solver_sha": FORWARD_SHA,
              "dataset_id": manifest.get("dataset_id"),
              "validation_target_accessed": False}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
