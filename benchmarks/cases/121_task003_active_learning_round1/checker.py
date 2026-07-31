"""Independent checker for the eight-point M3S Round-1 plan."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
PLAN = REPO / "surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/outcomes/ACTIVE_LEARNING_ROUND1_PLAN.json"
CONTRACT = REPO / "surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/outcomes/FEATURE_CONTRACT_v2.json"
DATA = REPO / "benchmarks/artifacts/cases/119/m4e/compact_dataset"
POOL = REPO / "benchmarks/cases/116_task002_single_fidelity_design/candidate_pool.json"
DESIGN = ROOT / "round1_design.json"
BASELINE = "10e3356ba8364286a452077f71d7e3b92ea24cd5"
POOL_HASH = "a9831ffc1055732660bee859382f623e8558560634d9ac98702cfe355ff09fcd"


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def points(design):
    return [[float(p[k]) for k in ("height_nm", "width_x_nm", "grazing_deg", "azimuth_deg")] for p in design["points"]]


def main() -> int:
    plan = json.loads(PLAN.read_text()); design = json.loads(DESIGN.read_text())
    pool = json.loads(POOL.read_text())
    contract = json.loads(CONTRACT.read_text())
    checks = {
        "feature_B_frozen": contract.get("frozen_candidate") == "B",
        "candidate_pool_hash": pool.get("point_tuple_sha256") == POOL_HASH,
        "plan_candidate_pool_hash": plan.get("candidate_pool_sha256") == POOL_HASH,
        "plan_budget_8": plan.get("budget") == 8 and len(plan.get("points", [])) == 8,
        "design_count_8": design.get("point_count") == 8 and len(design.get("points", [])) == 8,
        "design_schema": design.get("schema_version") == "task002.m3r-design.v1",
        "baseline_clean_sha": design.get("source_sha") == BASELINE and design.get("source_dirty") is False,
        "production_identity": design.get("production_model_id") == "S_PROD_FULL3D_STATIC_P5_H10_NY4" and design.get("production_solver_route_id") == "full3d_static_uniform_n1curl_p5_h10_ny4",
        "mesh_identity": plan.get("mesh", {}).get("axis_cell_counts") == [6, 4, 14] and plan.get("mesh", {}).get("degree") == 5,
        "next_round_not_authorized": plan.get("next_round_authorized") is False,
        "validation_target_not_accessed": plan.get("frozen_validation_target_accessed") is False,
    }
    plan_points = [row["point"] for row in plan["points"]]
    design_points = points(design)
    checks["plan_design_points_equal"] = plan_points == design_points
    checks["plan_tuple_hash"] = canonical(plan_points) == plan.get("point_tuple_sha256")
    checks["design_tuple_hash"] = canonical(design_points) == design.get("point_tuple_sha256")
    checks["unique_points"] = len({tuple(p) for p in design_points}) == 8
    train = np.load(DATA / "inputs.npy", allow_pickle=False)[np.load(DATA / "train_indices.npy", allow_pickle=False)]
    existing = [train]
    for name in ("frozen_validation_design.json", "discretization_audit_design.json"):
        d = json.loads((REPO / "benchmarks/cases/116_task002_single_fidelity_design" / name).read_text())
        existing.append(np.asarray(points(d), dtype=float))
    chosen = np.asarray(design_points, dtype=float)
    checks["no_existing_or_near_duplicate"] = bool(np.min(np.linalg.norm(chosen[:, None, :] - np.vstack(existing)[None, :, :], axis=2)) > 1.0e-8)
    labels = [set(row.get("region_labels", [])) for row in plan["points"]]
    checks["regime_coverage"] = all(any(name in row for row in labels) for name in ("low_grazing", "cutoff", "high_azimuth", "interior"))
    checks["exactly_eight_case119_identity_points"] = all(row.get("source_sha") == BASELINE and row.get("model_id") == "S_PROD_FULL3D_STATIC_P5_H10_NY4" for row in plan["points"])
    record_files = sorted((ROOT / "records").glob("*.json"))
    checks["eight_adapter_records"] = len(record_files) == 8
    adapter_rows = [json.loads(path.read_text()) for path in record_files]
    checks["adapter_identity_and_gates"] = all(
        row.get("source_sha") == BASELINE
        and row.get("source_dirty") is False
        and row.get("model_id") == "S_PROD_FULL3D_STATIC_P5_H10_NY4"
        and row.get("solver_route_id") == "full3d_static_uniform_n1curl_p5_h10_ny4"
        and row.get("status") == "measured_pass"
        and all(row.get("numerical_gates", {}).values())
        and all(row.get("resource_gates", {}).values())
        for row in adapter_rows
    )
    retry_manifest = REPO / "benchmarks/artifacts/cases/121_task003_active_learning_round1_retry_cachefix/campaign_manifest.json"
    if retry_manifest.exists():
        campaign = json.loads(retry_manifest.read_text())
        checks["campaign_eight_measured_pass"] = sum(v.get("status") == "measured_pass" for v in campaign.get("samples", {}).values()) == 8
        checks["campaign_no_failure"] = campaign.get("stop_reason") is None
    else:
        checks["campaign_eight_measured_pass"] = False
        checks["campaign_no_failure"] = False
    new_dataset = REPO / "benchmarks/artifacts/cases/121_task003_active_learning_round1_retry_cachefix/compact_dataset"
    if (new_dataset / "dataset_manifest.json").exists():
        dm = json.loads((new_dataset / "dataset_manifest.json").read_text())
        checks["new_dataset_104_plus_16"] = dm.get("sample_count") == 120 and dm.get("training_count") == 104 and dm.get("frozen_validation_count") == 16
        checks["new_dataset_source_identity"] = dm.get("dataset_source_sha") == BASELINE and dm.get("production_axis_cell_counts") == [6, 4, 14]
        checks["new_dataset_validation_sealed"] = dm.get("validation_target_accessed") is False
    else:
        checks["new_dataset_104_plus_16"] = False
        checks["new_dataset_source_identity"] = False
        checks["new_dataset_validation_sealed"] = False
    status = "pass" if all(checks.values()) else "fail"
    result = {"status": status, "checks": checks, "point_count": 8,
              "plan_tuple_sha256": plan.get("point_tuple_sha256"),
              "design_tuple_sha256": design.get("point_tuple_sha256"),
              "validation_target_accessed": False}
    (ROOT / "expected.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
