"""Independent exact-design checker for M3T and the authorized Round-2 run.

Only input arrays are opened.  Observable/target arrays are verified through
their declared identities and file hashes, so this checker cannot unlock or
score the frozen validation targets.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
OUT = REPO / "surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/outcomes"
DATA = REPO / "benchmarks/artifacts/cases/122_task003_round2/compact_dataset"
OLD = REPO / "benchmarks/artifacts/cases/119/m4e/compact_dataset"
DESIGN_ROOT = REPO / "benchmarks/cases/116_task002_single_fidelity_design"
ROUND1 = REPO / "benchmarks/cases/121_task003_active_learning_round1"
ROUND2 = REPO / "benchmarks/cases/122_task003_round2"
BASELINE = "10e3356ba8364286a452077f71d7e3b92ea24cd5"


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def tuples_from_design(path: Path):
    design = json.loads(path.read_text())
    return [[float(row[k]) for k in ("height_nm", "width_x_nm", "grazing_deg", "azimuth_deg")] for row in design["points"]]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    status = json.loads((OUT / "ROUND1_COMPLETION_STATUS.json").read_text())
    manifest = json.loads((DATA / "dataset_manifest.json").read_text())
    files = json.loads((DATA / "file_hashes.json").read_text())
    campaign = json.loads((REPO / "benchmarks/artifacts/cases/122_task003_round2/campaign_manifest.json").read_text())
    checks = {
        "m3t_status_authorized": status.get("round2_authorized") is True,
        "m3t_gate_positive": all(value for key, value in status.get("round2_gate", {}).items()
                                   if key != "validation_target_accessed"),
        "validation_target_accessed_false": status.get("validation_target_accessed") is False
            and status.get("round2_gate", {}).get("validation_target_accessed") is False,
        "manifest_112_plus_16": manifest.get("sample_count") == 128
            and manifest.get("training_count") == 112
            and manifest.get("frozen_validation_count") == 16,
        "manifest_identity": manifest.get("dataset_source_sha") == BASELINE
            and manifest.get("production_model_id") == "S_PROD_FULL3D_STATIC_P5_H10_NY4"
            and manifest.get("production_solver_route_id") == "full3d_static_uniform_n1curl_p5_h10_ny4",
        "fold_reference_present": json.loads((OUT / "BASE96_REFERENCE_FOLDS.json").read_text()).get("training_count") == 96,
        "fixed_reference_learning_curve": (OUT / "LEARNING_CURVE_FIXED_REFERENCE.json").exists()
            and json.loads((OUT / "LEARNING_CURVE_FIXED_REFERENCE.json").read_text()).get("sizes") == [96, 104, 112],
        "prospective_audit_present": (OUT / "ROUND1_FIXED_REFERENCE_AUDIT.json").exists()
            and json.loads((OUT / "ROUND1_FIXED_REFERENCE_AUDIT.json").read_text()).get("validation_target_accessed") is False,
        "round1_adapter_count": len(list((ROUND1 / "records").glob("*.json"))) >= 8,
        "round2_campaign_exactly_eight_pass": len(campaign.get("samples", {})) == 8
            and sum(row.get("status") == "measured_pass" for row in campaign.get("samples", {}).values()) == 8
            and not any(row.get("status") in {"failed_numerical_gate", "controlled_stop_resource"}
                        for row in campaign.get("samples", {}).values()),
        "round2_adapter_count": len(list((ROUND2 / "records").glob("*.json"))) == 8,
    }
    # Mmap only inputs; no aggregate/power/validation target array is loaded.
    new_inputs = np.load(DATA / "inputs.npy", mmap_mode="r", allow_pickle=False)
    new_train = np.load(DATA / "train_indices.npy", allow_pickle=False)
    new_validation = np.load(DATA / "frozen_validation_indices.npy", allow_pickle=False)
    old_inputs = np.load(OLD / "inputs.npy", mmap_mode="r", allow_pickle=False)
    old_train = np.load(OLD / "train_indices.npy", allow_pickle=False)
    checks["input_shapes"] = new_inputs.shape == (128, 4) and new_train.shape == (112,) and new_validation.shape == (16,)
    checks["original96_exact"] = bool(np.array_equal(new_inputs[:96], old_inputs[old_train]))
    checks["split_partition"] = bool(np.array_equal(np.sort(np.concatenate((new_train, new_validation))), np.arange(128)))
    checks["train_tuple_hash_rebuild"] = canonical(new_inputs[new_train].tolist()) == manifest.get("train_tuple_sha256")
    checks["validation_tuple_hash_rebuild"] = canonical(new_inputs[new_validation].tolist()) == manifest.get("frozen_validation_tuple_sha256")
    validation_design = tuples_from_design(DESIGN_ROOT / "frozen_validation_design.json")
    checks["frozen_validation_tuple_unchanged"] = canonical(new_inputs[new_validation].tolist()) == canonical(validation_design)
    round1_design = tuples_from_design(ROUND1 / "round1_design.json")
    round2_design = tuples_from_design(ROOT / "round2_design.json")
    checks["round1_eight_exact"] = canonical(new_inputs[112:120].tolist()) == canonical(round1_design)
    checks["round2_eight_exact"] = canonical(new_inputs[120:128].tolist()) == canonical(round2_design)
    checks["no_train_duplicates"] = len({tuple(row) for row in new_inputs[new_train].tolist()}) == 112
    checks["dataset_file_hashes_rebuild"] = all(files.get(name) == sha256(DATA / name)
                                                 for name in files if name != "file_hashes.json")

    plan_path = OUT / "ACTIVE_LEARNING_ROUND2_PLAN.json"
    design_path = ROOT / "round2_design.json"
    plan = json.loads(plan_path.read_text())
    design = json.loads(design_path.read_text())
    plan_points = [row["point"] for row in plan.get("points", [])]
    design_points = tuples_from_design(design_path)
    labels = [row.get("region_labels", {}) for row in plan.get("points", [])]
    checks["round2_plan_eight"] = len(plan_points) == 8 and design.get("point_count") == 8
    checks["round2_plan_identity"] = (plan.get("baseline_sha") == BASELINE
        and plan.get("model_id") == "S_PROD_FULL3D_STATIC_P5_H10_NY4"
        and plan.get("solver_route_id") == "full3d_static_uniform_n1curl_p5_h10_ny4"
        and plan.get("validation_target_accessed") is False)
    checks["round2_plan_design_match"] = plan_points == design_points and canonical(plan_points) == plan.get("point_tuple_sha256") == design.get("point_tuple_sha256")
    checks["round2_diversity"] = (sum(bool(x.get("low_grazing")) for x in labels) <= 3
        and sum(bool(x.get("high_grazing")) for x in labels) >= 2
        and sum(bool(x.get("high_azimuth")) for x in labels) >= 2
        and sum(bool(x.get("ordinary_interior")) for x in labels) >= 2
        and len({x.get("signature") for x in labels}) >= 4
        and len({x.get("h_bin") for x in labels}) >= 3
        and len({x.get("w_bin") for x in labels}) >= 3)
    pre_round2_train = np.asarray(list(range(96)) + list(range(112, 120)), dtype=np.int64)
    blocked = np.vstack((new_inputs[pre_round2_train], np.asarray(validation_design),
                         np.asarray(tuples_from_design(DESIGN_ROOT / "discretization_audit_design.json"))))
    checks["round2_unique_and_not_existing"] = len({tuple(row) for row in plan_points}) == 8 and bool(
        np.min(np.linalg.norm(np.asarray(plan_points)[:, None, :] - blocked[None, :, :], axis=2)) > 1.0e-8)
    checks["round2_plan_status_complete"] = plan.get("status") == "checker_pass"
    result = {"status": "pass" if all(checks.values()) else "fail", "checks": checks,
              "validation_target_accessed": False, "training_count": 112,
              "frozen_validation_count": 16, "round2_count": 8}
    (ROOT / "expected.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
