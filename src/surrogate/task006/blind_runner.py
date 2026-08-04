"""Sequential Task006 blind12 x A05/A07/A09 forward campaign.

The runner refuses to start unless the immutable M2R model lock exists.  It
does not read blind responses before launching their corresponding fixed
forward solve and never changes model or gate settings from a blind result.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any

from .design import (
    ANGLES,
    BLIND_GEOMETRIES,
    FORWARD_SOLVER_SHA,
    MODEL_ID,
    OBSERVABLE_SCHEMA,
    ROUTE_ID,
    canonical_hash,
    file_hash,
)


ROOT = Path(__file__).resolve().parents[3]
FORWARD_ROOT = Path("/tmp/MyFEniCS-forward-fdf9615-verified")
CASE_ID = "task006_fixed_A05_A07_A09_hw_blind12_v1"
ARTIFACT_ROOT = ROOT / "benchmarks/artifacts/cases/141_task006_blind12_forward"
OUTCOMES = ROOT / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes"
LOCK_PATH = OUTCOMES / "TASK006_MODEL_SELECTION_LOCK.json"


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def _rows() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    index = 0
    for geometry in BLIND_GEOMETRIES:
        for angle_id, grazing, azimuth in ANGLES:
            key = f"{geometry[0]:g},{geometry[1]:g}/{angle_id}"
            rows[key] = {
                "key": key, "height_nm": geometry[0], "width_nm": geometry[1],
                "angle_id": angle_id, "grazing_deg": grazing, "azimuth_deg": azimuth,
                "design_index": index,
                "point_tuple": [geometry[0], geometry[1], grazing, azimuth],
                "point_hash": canonical_hash({"design_id": CASE_ID, "design_index": index,
                                               "point_tuple": [geometry[0], geometry[1], grazing, azimuth]}),
                "run_directory": str((ARTIFACT_ROOT / "blind" / f"{geometry[0]:g}_{geometry[1]:g}" / angle_id).resolve()),
                "status": "reserved_blind_fem", "attempted": False, "attempt_number": 0,
                "sample_path": None, "formal_record_path": None,
                "formal_record_sha256": None, "execution_sha256": None,
            }
            index += 1
    return rows


def _preflight(forward_root: Path) -> dict[str, Any]:
    driver = ROOT / "src/surrogate/doe/forward_driver.py"
    run_directory = ARTIFACT_ROOT / "preflight"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
    command = [str(ROOT / ".venv/bin/python"), str(driver),
               "--forward-root", str(forward_root), "--baseline-sha", FORWARD_SOLVER_SHA,
               "--run-directory", str(run_directory), "--preflight-only"]
    completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    payload = {"return_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr,
               "status": "pass" if completed.returncode == 0 else "failed"}
    _write(OUTCOMES / "BLIND12_RESOURCE_PREFLIGHT.json", payload)
    if completed.returncode != 0:
        raise RuntimeError("blind forward ABI/resource preflight failed")
    return payload


def _command(row: dict[str, Any], forward_root: Path) -> list[str]:
    return [str(ROOT / ".venv/bin/python"), str(ROOT / "src/surrogate/doe/forward_driver.py"),
            "--forward-root", str(forward_root), "--baseline-sha", FORWARD_SOLVER_SHA,
            "--run-directory", row["run_directory"], "--height", str(row["height_nm"]),
            "--width", str(row["width_nm"]), "--grazing", str(row["grazing_deg"]),
            "--azimuth", str(row["azimuth_deg"]), "--design-id", CASE_ID,
            "--design-index", str(row["design_index"]), "--split", "blind",
            "--sample-name", "task006_production_sample.json", "--timeout-seconds", "1800"]


def _run_one(row: dict[str, Any], forward_root: Path, heartbeat_seconds: float) -> int:
    run_directory = Path(row["run_directory"])
    if run_directory.exists():
        raise RuntimeError(f"blind run directory already exists: {run_directory}")
    log_path = ARTIFACT_ROOT / "blind_logs" / (row["key"].replace("/", "__").replace(",", "_") + ".log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(_command(row, forward_root), cwd=ROOT, env=env,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        started = time.monotonic(); next_heartbeat = started + heartbeat_seconds
        while True:
            code = process.poll()
            if code is not None:
                return int(code)
            now = time.monotonic()
            if now >= next_heartbeat:
                print(f"blind heartbeat {row['key']}: alive elapsed={now-started:.0f}s", flush=True)
                next_heartbeat = now + heartbeat_seconds
            time.sleep(1.0)


def _load_summary(row: dict[str, Any]) -> dict[str, Any]:
    path = Path(row["run_directory"]) / "task005_driver_summary.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def run(*, forward_root: Path = FORWARD_ROOT, resume: bool = True,
        heartbeat_seconds: float = 30.0) -> dict[str, Any]:
    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("status") != "locked_for_blind" or lock.get("blind_fem_run") is not False:
        raise RuntimeError("Task006 model lock is missing or blind run was already recorded")
    if lock.get("forward_solver_sha") != FORWARD_SOLVER_SHA or lock.get("fixed_angle_order") != [a[0] for a in ANGLES]:
        raise RuntimeError("model lock identity mismatch")
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = ARTIFACT_ROOT / "BLIND12_CAMPAIGN.json"
    rows = _rows()
    payload: dict[str, Any] = {
        "schema_version": "task006.blind12-campaign.v1", "campaign_id": CASE_ID,
        "status": "reserved", "stop_reason": None,
        "model_lock_path": str(LOCK_PATH), "model_lock_sha256": file_hash(LOCK_PATH),
        "forward_solver_sha": FORWARD_SOLVER_SHA, "model_id": MODEL_ID,
        "solver_route_id": ROUTE_ID, "observable_schema_version": OBSERVABLE_SCHEMA,
        "fixed_angle_order": [a[0] for a in ANGLES], "blind_geometry_count": len(BLIND_GEOMETRIES),
        "expected_record_count": 36, "expected_new_fem_count": 36,
        "new_fem_count": 0, "blind_response_accessed": False,
        "validation_target_accessed": False, "model_tuned_after_blind": False,
        "records": rows,
    }
    if manifest_path.is_file() and resume:
        old = json.loads(manifest_path.read_text())
        if old.get("campaign_id") != CASE_ID or old.get("model_lock_sha256") != payload["model_lock_sha256"]:
            raise RuntimeError("existing blind campaign has incompatible lock identity")
        payload = old
    else:
        _write(manifest_path, payload)
    _preflight(forward_root.resolve())
    for key, row in payload["records"].items():
        sample_path = Path(row["run_directory"]) / "task006_production_sample.json"
        if resume and row.get("status") == "measured_pass" and sample_path.is_file():
            continue
        if Path(row["run_directory"]).exists():
            payload["status"] = "controlled_stop"; payload["stop_reason"] = f"unexpected_existing_run_directory:{key}"
            _write(manifest_path, payload)
            raise RuntimeError(payload["stop_reason"])
        row["attempted"] = True; row["attempt_number"] = int(row.get("attempt_number", 0)) + 1
        row["status"] = "running"; _write(manifest_path, payload)
        print(f"blind start {key}: h={row['height_nm']} w={row['width_nm']} g={row['grazing_deg']} a={row['azimuth_deg']}", flush=True)
        code = _run_one(row, forward_root, heartbeat_seconds)
        summary = _load_summary(row)
        row.update({"return_code": code, "status": summary.get("status", "failed_runner"),
                    "sample_path": summary.get("sample_path"), "formal_record_path": summary.get("formal_record_path"),
                    "formal_record_sha256": summary.get("formal_record_sha256"),
                    "execution_sha256": summary.get("execution_sha256"), "source_sha": summary.get("source_sha")})
        payload["new_fem_count"] = int(payload.get("new_fem_count", 0)) + 1
        _write(manifest_path, payload)
        if code != 0 or row["status"] != "measured_pass" or not row.get("sample_path"):
            print(f"blind recorded failure {key}: {row['status']}; continuing fixed batch", flush=True)
    payload["record_count"] = len(payload["records"])
    payload["pass_count"] = sum(row.get("status") == "measured_pass" for row in payload["records"].values())
    payload["failure_count"] = payload["record_count"] - payload["pass_count"]
    payload["status"] = "pass" if payload.get("new_fem_count") == 36 and payload["failure_count"] == 0 else "completed_with_failures"
    payload["stop_reason"] = None if payload["status"] == "pass" else "one_or_more_blind_records_failed"
    _write(manifest_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forward-root", type=Path, default=FORWARD_ROOT)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    args = parser.parse_args()
    result = run(forward_root=args.forward_root.resolve(), resume=not args.no_resume,
                 heartbeat_seconds=args.heartbeat_seconds)
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
