"""Sequential Task006 M1 training campaign.

The runner reserves all 111 training records, reuses only the 32 exact
Task005/Task004 records listed by the frozen M0 inventory, and launches one
fresh-process forward solve at a time for the remaining 79 records.  It never
constructs a path from the 12 blind tuples.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
from typing import Any

from .design import (
    ANGLES,
    FORWARD_SOLVER_SHA,
    MODEL_ID,
    OBSERVABLE_SCHEMA,
    ROUTE_ID,
    TRAIN_GEOMETRIES,
    expected_reuse_sources,
)


ROOT = Path(__file__).resolve().parents[3]
FORWARD_ROOT = Path("/tmp/MyFEniCS-forward-fdf9615-verified")
CASE_ID = "task006_fixed_A05_A07_A09_hw_train37_p5_ny4_v1"
ARTIFACT_ROOT = ROOT / "benchmarks/artifacts/cases/136_task006_train37_forward"
OUTCOMES = ROOT / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes"


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def _source_rows() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    sources = expected_reuse_sources(ROOT)
    angle_map = {aid: (g, a) for aid, g, a in ANGLES}
    for geometry in TRAIN_GEOMETRIES:
        for angle_id, grazing, azimuth in ANGLES:
            key = f"{geometry[0]:g},{geometry[1]:g}/{angle_id}"
            source = sources.get(key)
            result[key] = {
                "key": key, "height_nm": geometry[0], "width_nm": geometry[1],
                "angle_id": angle_id, "grazing_deg": grazing, "azimuth_deg": azimuth,
                "design_index": len(result),
                "source_kind": source["source_kind"] if source else None,
                "reuse": source is not None,
                "source_path": source["path"] if source else None,
                "line_match": source["line_match"] if source else None,
                "run_directory": str((ARTIFACT_ROOT / "m1" / f"{geometry[0]:g}_{geometry[1]:g}" / angle_id).resolve()) if source is None else None,
                "sample_path": None,
                "status": "reserved_reuse" if source else "reserved_new_fem",
                "attempted": False, "attempt_number": 0,
            }
    return result


def _m0_check() -> None:
    checker = ROOT / "benchmarks/cases/135_task006_m0_design_and_reuse/checker.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
    completed = subprocess.run(
        [str(ROOT / ".venv/bin/python"), str(checker), "--root", str(ROOT)],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    (OUTCOMES / "M1_M0_CHECKER.txt").write_text(completed.stdout + completed.stderr)
    if completed.returncode != 0:
        raise RuntimeError("Task006 M0 checker failed; no M1 FEM launched")


def _preflight(forward_root: Path) -> None:
    driver = ROOT / "src/surrogate/doe/forward_driver.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
    run_dir = ARTIFACT_ROOT / "preflight"
    command = [str(ROOT / ".venv/bin/python"), str(driver), "--forward-root", str(forward_root),
               "--baseline-sha", FORWARD_SOLVER_SHA, "--run-directory", str(run_dir), "--preflight-only"]
    completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    (OUTCOMES / "M1_RESOURCE_PREFLIGHT.json").write_text(completed.stdout + completed.stderr)
    if completed.returncode != 0:
        raise RuntimeError("forward ABI/resource preflight failed; no M1 FEM launched")


def _command(row: dict[str, Any], forward_root: Path) -> list[str]:
    driver = ROOT / "src/surrogate/doe/forward_driver.py"
    return [
        str(ROOT / ".venv/bin/python"), str(driver), "--forward-root", str(forward_root),
        "--baseline-sha", FORWARD_SOLVER_SHA, "--run-directory", row["run_directory"],
        "--height", str(row["height_nm"]), "--width", str(row["width_nm"]),
        "--grazing", str(row["grazing_deg"]), "--azimuth", str(row["azimuth_deg"]),
        "--design-id", CASE_ID, "--design-index", str(row["design_index"]),
        "--split", "training", "--sample-name", "task006_production_sample.json",
        "--timeout-seconds", "1800",
    ]


def _run_one(row: dict[str, Any], *, forward_root: Path, heartbeat_seconds: float) -> int:
    run_directory = Path(row["run_directory"])
    if run_directory.exists():
        raise RuntimeError(f"reserved run directory already exists: {run_directory}")
    log_name = row["key"].replace("/", "__").replace(",", "_") + ".log"
    log_path = ARTIFACT_ROOT / "m1_logs" / log_name
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
    command = _command(row, forward_root)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        started = time.monotonic(); next_heartbeat = started + heartbeat_seconds
        while True:
            return_code = process.poll()
            if return_code is not None:
                return int(return_code)
            now = time.monotonic()
            if now >= next_heartbeat:
                print(f"M1 heartbeat {row['key']}: alive elapsed={now-started:.0f}s", flush=True)
                next_heartbeat = now + heartbeat_seconds
            time.sleep(1.0)


def _load_summary(row: dict[str, Any]) -> dict[str, Any]:
    path = Path(row["run_directory"]) / "task005_driver_summary.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text())


def run(*, resume: bool = True, forward_root: Path = FORWARD_ROOT,
        heartbeat_seconds: float = 30.0) -> dict[str, Any]:
    """Run or resume the exact 79-new-solve M1 campaign."""

    OUTCOMES.mkdir(parents=True, exist_ok=True)
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = ARTIFACT_ROOT / "M1_TRAIN37_CAMPAIGN.json"
    rows = _source_rows()
    payload: dict[str, Any] = {
        "schema_version": "task006.m1-train37-campaign.v1",
        "campaign_id": CASE_ID, "status": "reserved", "stop_reason": None,
        "forward_solver_sha": FORWARD_SOLVER_SHA, "model_id": MODEL_ID,
        "solver_route_id": ROUTE_ID, "observable_schema_version": OBSERVABLE_SCHEMA,
        "mpi_ranks": 2, "threads_per_rank": 1, "mumps_icntl_14": 40,
        "max_parallel_forward_solves": 1, "expected_training_geometries": 37,
        "expected_record_count": 111, "expected_reuse_count": 32,
        "expected_new_fem_count": 79, "new_fem_count": 0,
        "blind_response_accessed": False, "validation_target_accessed": False,
        "records": rows,
    }
    if manifest_path.is_file() and resume:
        old = json.loads(manifest_path.read_text())
        if old.get("campaign_id") != CASE_ID or old.get("forward_solver_sha") != FORWARD_SOLVER_SHA:
            raise RuntimeError("existing Task006 M1 manifest has incompatible identity")
        payload = old
    else:
        _write(manifest_path, payload)

    _m0_check()
    _preflight(forward_root)
    records = payload["records"]
    for key, row in records.items():
        if row.get("reuse"):
            source = Path(row["source_path"])
            if not source.is_file():
                payload["status"] = "controlled_stop"; payload["stop_reason"] = f"missing_reuse:{key}"
                _write(manifest_path, payload)
                raise RuntimeError(payload["stop_reason"])
            row["status"] = "reused_exact"
            row["sample_path"] = row["source_path"]
            continue
        sample_path = Path(row["run_directory"]) / "task006_production_sample.json"
        if row.get("status") == "measured_pass" and sample_path.is_file() and resume:
            continue
        if Path(row["run_directory"]).exists():
            payload["status"] = "controlled_stop"; payload["stop_reason"] = f"unexpected_existing_run_directory:{key}"
            _write(manifest_path, payload)
            raise RuntimeError(payload["stop_reason"])
        row["attempted"] = True; row["attempt_number"] = int(row.get("attempt_number", 0)) + 1
        row["status"] = "running"
        _write(manifest_path, payload)
        print(f"M1 start {key}: h={row['height_nm']} w={row['width_nm']} g={row['grazing_deg']} a={row['azimuth_deg']}", flush=True)
        code = _run_one(row, forward_root=forward_root, heartbeat_seconds=heartbeat_seconds)
        summary = _load_summary(row)
        row.update({
            "return_code": code, "status": summary.get("status", "failed_runner"),
            "sample_path": summary.get("sample_path"),
            "formal_record_path": summary.get("formal_record_path"),
            "formal_record_sha256": summary.get("formal_record_sha256"),
            "execution_sha256": summary.get("execution_sha256"),
            "source_sha": summary.get("source_sha"),
        })
        payload["new_fem_count"] = int(payload.get("new_fem_count", 0)) + 1
        _write(manifest_path, payload)
        if code != 0 or row["status"] != "measured_pass" or not row.get("sample_path"):
            payload["status"] = "controlled_stop"; payload["stop_reason"] = f"first_unexplained_failure:{key}:{row['status']}"
            _write(manifest_path, payload)
            print(f"M1 STOP {payload['stop_reason']}", flush=True)
            return payload

    if int(payload.get("new_fem_count", 0)) != 79:
        payload["status"] = "controlled_stop"; payload["stop_reason"] = "new_fem_budget_not_exactly_79"
    else:
        payload["status"] = "pass"; payload["stop_reason"] = None
    payload["reuse_count"] = sum(1 for row in records.values() if row.get("reuse"))
    payload["record_count"] = len(records)
    _write(manifest_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forward-root", type=Path, default=FORWARD_ROOT)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    args = parser.parse_args()
    result = run(resume=not args.no_resume, forward_root=args.forward_root.resolve(), heartbeat_seconds=args.heartbeat_seconds)
    print(json.dumps({k: v for k, v in result.items() if k != "records"}, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
