"""Task005 M4 off-centre recovery campaign (maximum nine fresh FEM states)."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
from typing import Any

from .design import FORWARD_SOLVER_SHA, MODEL_ID, ROUTE_ID
from .recovery import recover_geometry, write_recovery_design
from .runner import FORWARD_ROOT, SURROGATE_ROOT, _command, _run_with_heartbeat


ANGLE_IDS = ["A05", "A07", "A09"]
GEOMETRIES = {
    "G1": (118.75, 16.75), "G2": (121.25, 17.25), "G3": (118.75, 17.25),
}
CASE_ID = "task005_m4_recovery_v1"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def _rows(artifact_root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    index = 0
    angle_map = {row[0]: (float(row[1]), float(row[2])) for row in __import__("src.surrogate.doe.design", fromlist=["ANGLE_CANDIDATES"]).ANGLE_CANDIDATES}
    for geometry_id, (height, width) in GEOMETRIES.items():
        for angle_id in ANGLE_IDS:
            grazing, azimuth = angle_map[angle_id]
            key = f"{geometry_id}/{angle_id}"
            result[key] = {
                "key": key, "geometry_id": geometry_id, "angle_id": angle_id,
                "design_index": index, "height_nm": height, "width_nm": width,
                "grazing_deg": grazing, "azimuth_deg": azimuth,
                "run_directory": str((artifact_root / "m4" / geometry_id / angle_id).resolve()),
                "status": "reserved", "new_fem": True,
            }
            index += 1
    return result


def run_m4(*, outcomes_dir: Path, dataset_dir: Path, artifact_root: Path,
           forward_root: Path = FORWARD_ROOT, timeout_seconds: float = 1800.0,
           resume: bool = True) -> dict[str, Any]:
    ranking_path = outcomes_dir / "FISHER_COMBINATION_RANKING.json"
    dataset_manifest = json.loads((dataset_dir / "dataset_manifest.json").read_text())
    ranking = json.loads(ranking_path.read_text())
    selected = ranking.get("recommended_triple")
    if not selected or selected.get("angle_ids") != ANGLE_IDS:
        raise RuntimeError("M4 selected triple is not the frozen robust ranking result")
    design_path = outcomes_dir / "OFF_CENTRE_RECOVERY_DESIGN.json"
    if design_path.is_file() and resume:
        design = json.loads(design_path.read_text())
        if design.get("selected_angle_ids") != ANGLE_IDS or design.get("status") != "frozen":
            raise RuntimeError("existing M4 recovery design changed")
    else:
        design = write_recovery_design(
            design_path, angle_ids=ANGLE_IDS,
            ranking_sha256=_digest(ranking_path),
            dataset_manifest_sha256=_digest(dataset_dir / "dataset_manifest.json"),
        )
    manifest_path = outcomes_dir / "M4_RECOVERY_CAMPAIGN.json"
    records = _rows(artifact_root)
    payload = {
        "schema_version": "task005.m4-recovery-campaign.v1", "campaign_id": CASE_ID,
        "forward_solver_sha": FORWARD_SOLVER_SHA, "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
        "selected_angle_ids": ANGLE_IDS, "geometry_ids": list(GEOMETRIES),
        "max_new_fem": 9, "new_fem_count": 9, "status": "reserved", "stop_reason": None,
        "validation_target_accessed": False, "records": records,
        "design_sha256": _digest(design_path),
    }
    if manifest_path.is_file() and resume:
        old = json.loads(manifest_path.read_text())
        if old.get("design_sha256") != payload["design_sha256"]:
            raise RuntimeError("M4 recovery design hash changed")
        payload["records"] = old.get("records", records)
    _write(manifest_path, payload)
    driver = SURROGATE_ROOT / "src/surrogate/doe/forward_driver.py"
    for key, row in payload["records"].items():
        if row.get("status") == "measured_pass" and row.get("sample_path") and Path(row["sample_path"]).is_file() and resume:
            continue
        print(f"M4 start {key}: h={row['height_nm']} w={row['width_nm']} g={row['grazing_deg']} a={row['azimuth_deg']}", flush=True)
        row["attempted"] = True; row["attempt_number"] = int(row.get("attempt_number", 0)) + 1; row["status"] = "running"
        _write(manifest_path, payload)
        command = _command(root=forward_root, driver=driver, row=row,
                           baseline_sha=FORWARD_SOLVER_SHA, timeout_seconds=timeout_seconds)
        log_name = key.replace("/", "__") + ".log"
        return_code = _run_with_heartbeat(command, cwd=forward_root,
                                          log_path=artifact_root / "m4_logs" / log_name,
                                          label=key, phase="M4")
        summary_path = Path(row["run_directory"]) / "task005_driver_summary.json"
        summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
        row.update({"return_code": return_code, "status": summary.get("status", "failed_runner"),
                    "sample_path": summary.get("sample_path"), "formal_record_sha256": summary.get("formal_record_sha256"),
                    "execution_sha256": summary.get("execution_sha256"), "watchdog": summary.get("watchdog")})
        _write(manifest_path, payload)
        if return_code != 0 or row["status"] != "measured_pass":
            payload["status"] = "controlled_stop"; payload["stop_reason"] = f"first_unexplained_failure:{key}:{row['status']}"
            _write(manifest_path, payload); return payload
    derivatives = json.loads((dataset_dir / "derivatives.json").read_text())
    dataset = {"dataset_id": dataset_manifest["dataset_id"], "angles": derivatives}
    all_results: dict[str, Any] = {}
    for geometry_id, (height, width) in GEOMETRIES.items():
        test_records = {
            angle_id: json.loads(Path(payload["records"][f"{geometry_id}/{angle_id}"]["sample_path"]).read_text())
            for angle_id in ANGLE_IDS
        }
        all_results[geometry_id] = recover_geometry(
            dataset=dataset, test_records=test_records, angle_ids=ANGLE_IDS,
            truth=(height - 120.0, width - 17.0),
        )
    result = {
        "schema_version": "task005.off-centre-recovery.v1", "status": "pass",
        "forward_solver_sha": FORWARD_SOLVER_SHA, "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
        "design_sha256": payload["design_sha256"], "selected_angle_ids": ANGLE_IDS,
        "geometries": all_results, "new_fem_count": 9, "validation_target_accessed": False,
        "primary_gate_all_geometries": bool(all(item["primary_gate"] for item in all_results.values())),
    }
    result["status"] = "pass" if result["primary_gate_all_geometries"] else "controlled_negative"
    _write(outcomes_dir / "OFF_CENTRE_RECOVERY.json", result)
    lines = ["# Task005 M4 off-centre recovery", "", f"Status: **{result['status']}**", "",
             "Primary qualification is M1 order-total with N1 provisional noise; M0 and M2 are reported diagnostically.", "",
             "| geometry | truth (dh,dw) nm | recovered (dh,dw) nm | abs error h | abs error w | primary Gate |",
             "|---|---|---|---:|---:|---|"]
    for gid, item in all_results.items():
        x = item["contracts"]["M1_order_total_robust"]["N1"]
        lines.append(f"| {gid} | ({item['truth_delta_h_nm']:.2f},{item['truth_delta_w_nm']:.2f}) | ({x['estimate_delta_h_nm']:.6f},{x['estimate_delta_w_nm']:.6f}) | {x['absolute_height_error_nm']:.6f} | {x['absolute_width_error_nm']:.6f} | {x['gate']} |")
    (outcomes_dir / "OFF_CENTRE_RECOVERY.md").write_text("\n".join(lines) + "\n")
    payload["status"] = "pass" if result["status"] == "pass" else "controlled_negative"
    payload["stop_reason"] = None if result["status"] == "pass" else "M4_primary_recovery_gate_failed"
    _write(manifest_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcomes", type=Path, default=SURROGATE_ROOT / "surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/outcomes")
    parser.add_argument("--dataset-dir", type=Path, default=SURROGATE_ROOT / "benchmarks/artifacts/cases/132_task005_sensitivity_dataset/dataset")
    parser.add_argument("--artifact-root", type=Path, default=SURROGATE_ROOT / "benchmarks/artifacts/cases/133_task005_off_centre_recovery")
    parser.add_argument("--forward-root", type=Path, default=FORWARD_ROOT)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    result = run_m4(outcomes_dir=args.outcomes.resolve(), dataset_dir=args.dataset_dir.resolve(),
                    artifact_root=args.artifact_root.resolve(), forward_root=args.forward_root.resolve(),
                    timeout_seconds=args.timeout_seconds, resume=not args.no_resume)
    print(json.dumps({"status": result.get("status"), "stop_reason": result.get("stop_reason"), "new_fem_count": result.get("new_fem_count")}, indent=2))
    return 0 if result.get("status") == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
