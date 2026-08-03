"""Independent post-FEM and train112 checker for Task004 M4F."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from src.surrogate.angle.dataset import verify_immutable_package


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
PLAN = REPO / "surrogate_tasks/task004_nominal_geometry_angle_surrogate/outcomes/ACTIVE_LEARNING_ROUND1_PLAN_V2.json"
DESIGN = ROOT / "records/round1_training_design.json"
COMBINED = ROOT / "records/train112_design.json"
CAMPAIGN = REPO / "benchmarks/artifacts/cases/127_task004_active_learning_round1/campaign_manifest.json"
FEM_ROOT = REPO / "benchmarks/artifacts/cases/127_task004_active_learning_round1/fem/task004_angle_training_round1_v1"
TRAIN96_DESIGN = REPO / "benchmarks/cases/123_task004_nominal_geometry_angle_surrogate/training_design.json"
TRAIN112 = REPO / "benchmarks/artifacts/cases/127_task004_active_learning_round1/train112"
OUT = ROOT / "records/case127_post_fem_check.json"
FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"


def canonical(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def tuple_rows(path: Path) -> list[list[float]]:
    return [[float(np.round(float(point[key]), 12)) for key in ("height_nm", "width_x_nm", "grazing_deg", "azimuth_deg")]
            for point in json.loads(path.read_text())["points"]]


def main() -> int:
    checks: dict[str, bool] = {}
    errors: list[str] = []
    plan = json.loads(PLAN.read_text()); design = json.loads(DESIGN.read_text())
    campaign = json.loads(CAMPAIGN.read_text())
    rows = campaign.get("samples", {})
    plan_tuples = [list(map(float, point["tuple"])) for point in plan["points"]]
    design_tuples = tuple_rows(DESIGN)
    checks["plan_design_identity"] = bool(
        plan.get("status") == "ready_for_m4f" and len(plan_tuples) == 16 and
        design.get("point_tuple_sha256") == canonical(design_tuples) and
        design_tuples == [[float(np.round(v, 12)) for v in row] for row in plan_tuples] and
        design.get("source_sha") == FORWARD_SHA and design.get("source_dirty") is False
    )
    statuses = [row.get("status") for row in rows.values()]
    checks["campaign_exact_16_pass"] = bool(
        campaign.get("baseline_sha") == FORWARD_SHA and len(rows) == 16 and
        statuses and all(status == "measured_pass" for status in statuses) and
        all(row.get("split") == "train" and row.get("source_sha") == FORWARD_SHA for row in rows.values())
    )
    record_ok = True
    resource_rows = []
    for key, row in rows.items():
        run = Path(row["run_directory"])
        record_path = run / "results/task002_full3d_record.json"
        execution_path = run / "execution.json"
        if not record_path.is_file() or not execution_path.is_file():
            record_ok = False
            continue
        record = json.loads(record_path.read_text()); execution = json.loads(execution_path.read_text())
        gates = record.get("gates", {}); watchdog = execution.get("watchdog", {})
        record_ok = bool(record_ok and record.get("source_sha") == FORWARD_SHA and
                         record.get("solver_route_id") == ROUTE_ID and
                         record.get("output_profile") == "compact_surrogate_record" and
                         record.get("actual_runtime_topology_identity", {}).get("axis_cell_counts") == [6, 4, 14] and
                         record.get("solver_identity", {}).get("requested_mat_mumps_icntl_14") == 40 and
                         record.get("solver_identity", {}).get("actual_mat_mumps_icntl_14") == 40 and
                         bool(gates) and all(gates.values()) and watchdog.get("status") == "completed" and
                         watchdog.get("return_code") == 0 and watchdog.get("peak_swap_bytes") == 0 and
                         watchdog.get("cleanup_complete") is True)
        resource_rows.append({"key": key, "elapsed_seconds": watchdog.get("elapsed_seconds"),
                              "peak_rss_bytes": watchdog.get("peak_rss_bytes"),
                              "peak_pss_bytes": watchdog.get("peak_pss_bytes"),
                              "peak_uss_bytes": watchdog.get("peak_uss_bytes"),
                              "peak_swap_bytes": watchdog.get("peak_swap_bytes")})
    checks["all_compact_records_and_gates"] = record_ok
    checks["train112_immutable_identity"] = False
    if TRAIN112.is_dir():
        try:
            manifest = verify_immutable_package(TRAIN112, expected_dataset_id="task004_angle_nominal_p5_ny4_train112_v1")
            checks["train112_immutable_identity"] = bool(
                manifest.get("sample_count") == 112 and manifest.get("training_count") == 112 and
                manifest.get("forward_solver_sha") == FORWARD_SHA and
                manifest.get("validation_target_accessed") is False and manifest.get("immutable") is True
            )
        except (ValueError, OSError) as exc:
            errors.append(f"train112 verification failed: {exc}")
    combined = json.loads(COMBINED.read_text()) if COMBINED.is_file() else {}
    expected_combined = tuple_rows(TRAIN96_DESIGN) + design_tuples
    checks["train112_exact_96_plus_16"] = bool(
        combined.get("point_count") == 112 and combined.get("point_tuple_sha256") == canonical(expected_combined) and
        tuple_rows(COMBINED) == expected_combined and combined.get("source_sha") == FORWARD_SHA and
        combined.get("source_dirty") is False
    )
    checks["validation_sealed"] = bool(
        json.loads((TRAIN112 / "dataset_manifest.json").read_text()).get("validation_target_accessed") is False
        if (TRAIN112 / "dataset_manifest.json").is_file() else False
    )
    checks["all_checks"] = bool(all(checks.values()) and not errors)
    result = {"schema_version": "case127.post-fem-check.v1",
              "status": "pass" if checks["all_checks"] else "fail",
              "checks": checks, "errors": errors, "resource_rows": resource_rows,
              "point_count": 16, "training_count": 112,
              "forward_solver_sha": FORWARD_SHA, "validation_target_accessed": False}
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
